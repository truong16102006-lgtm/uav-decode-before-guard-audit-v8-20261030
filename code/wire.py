"""UE8 versioned wire: uint64 fields, explicit linear escapes, EOS and checksums."""
import struct,math,zlib,binascii
from functools import lru_cache
import numpy as np

HEADER=struct.Struct('<4sdddd')
MAGICS={0:b'UE80',16:b'UE8H',32:b'UE8C'}
NORMAL=0;ESCAPE=1;EOS=255
AUDIT=0xa0
PROFILES={'fine':(.01,1e-7),'medium':(.1,1e-6),'coarse':(1.,1e-5)}

class Refusal(ValueError):pass

def uleb(n):
    n=int(n)
    if not 0<=n<2**64:raise Refusal('OVERFLOW_UINT64')
    out=bytearray()
    while n>=128:out.append((n&127)|128);n>>=7
    out.append(n);return bytes(out)

def read_uleb(buf,pos):
    value=0
    for shift in range(0,70,7):
        if pos>=len(buf):raise Refusal('TRUNCATED_ULEB')
        byte=buf[pos];pos+=1;value|=(byte&127)<<shift
        if not byte&128:
            if value>=2**64 or (shift and byte==0):raise Refusal('NONCANONICAL_ULEB')
            return value,pos
    raise Refusal('OVERFLOW_ULEB')

def header(origin,h,sp,se,crc=0):
    if crc not in MAGICS or not np.isfinite([origin,h,sp,se]).all() or min(h,sp,se)<=0:raise Refusal('INVALID_HEADER')
    return HEADER.pack(MAGICS[crc],origin,h,sp,se)

def tick(time,origin,h):
    n=round((time-origin)/h)
    if n<0 or origin+n*h!=time:raise Refusal('CLOCK_NOT_EXACT_TICK')
    return n

def normal(seq,ti,pc,ec):
    return bytes([NORMAL])+struct.pack('<H',int(seq)%65536)+uleb(ti)+uleb(pc)+uleb(ec)

def escape(seq,ti,power,energy):
    if not np.isfinite([power,energy]).all() or min(power,energy)<0:raise Refusal('INVALID_ESCAPE')
    return bytes([ESCAPE])+struct.pack('<H',int(seq)%65536)+uleb(ti)+struct.pack('<dd',power,energy)

def footer(seq,ti):return bytes([EOS])+struct.pack('<H',int(seq)%65536)+uleb(ti)

def audit_sample(ti,power):
    if not 0<=int(ti)<2**64 or not math.isfinite(power) or power<0:raise Refusal('INVALID_AUDIT_SAMPLE')
    return struct.pack('<BQd',AUDIT,int(ti),float(power))

def decode_audit_sample(blob):
    if len(blob)!=17:raise Refusal('INVALID_AUDIT_LENGTH')
    kind,ti,power=struct.unpack('<BQd',blob)
    if kind!=AUDIT or not math.isfinite(power) or power<0:raise Refusal('INVALID_AUDIT_SAMPLE')
    return ti,power

def checksum(buf,bits):
    if bits==32:return struct.pack('<I',zlib.crc32(buf)&0xffffffff)
    if bits==16:return struct.pack('<H',binascii.crc_hqx(buf,0xffff))
    if bits==0:return b''
    raise Refusal('INVALID_CRC_MODE')

def decode_packet(buf,pos,origin,h,sp,se):
    start=pos
    if pos+3>len(buf):raise Refusal('TRUNCATED_PACKET')
    kind=buf[pos];seq=struct.unpack_from('<H',buf,pos+1)[0];pos+=3;ti,pos=read_uleb(buf,pos)
    if not math.isfinite(origin+h*ti):raise Refusal('NONFINITE_DECODED_CLOCK')
    if kind==EOS:return dict(kind=kind,seq=seq,tick=ti,time=origin+h*ti,blob=bytes(buf[start:pos])),pos
    if kind==NORMAL:
        pc,pos=read_uleb(buf,pos);ec,pos=read_uleb(buf,pos);p=pc*sp;e=ec*se
    elif kind==ESCAPE:
        if pos+16>len(buf):raise Refusal('TRUNCATED_ESCAPE')
        p,e=struct.unpack_from('<dd',buf,pos);pos+=16
    else:raise Refusal('INVALID_PACKET_KIND')
    if not np.isfinite([origin+h*ti,p,e]).all() or min(p,e)<0:raise Refusal('INVALID_DECODED_FIELD')
    return dict(kind=kind,seq=seq,tick=ti,time=origin+h*ti,power=p,energy=e,blob=bytes(buf[start:pos])),pos

def decode(wire):
    if len(wire)<HEADER.size:raise Refusal('TRUNCATED_HEADER')
    magic,origin,h,sp,se=HEADER.unpack_from(wire)
    inverse={v:k for k,v in MAGICS.items()}
    if magic not in inverse or not np.isfinite([origin,h,sp,se]).all() or min(h,sp,se)<=0:raise Refusal('INVALID_HEADER')
    crc=inverse[magic];end=len(wire)-crc//8
    if crc and (end<HEADER.size or checksum(wire[:end],crc)!=wire[end:]):raise Refusal('CRC_MISMATCH')
    pos=HEADER.size;packets=[];endmark=None;body=memoryview(wire)[:end]
    while pos<end:
        item,pos=decode_packet(body,pos,origin,h,sp,se)
        if item['kind']==EOS:
            if pos!=end:raise Refusal('TRAILING_BYTES_AFTER_EOS')
            endmark=item;break
        if item['seq']!=len(packets)%65536:raise Refusal('INVALID_SEQUENCE')
        if packets and item['tick']<=packets[-1]['tick']:raise Refusal('INVALID_TICK_ORDER')
        packets.append(item)
    if len(packets)<2 or packets[0]['tick']!=0 or packets[0]['kind']!=NORMAL:raise Refusal('MISSING_START')
    if endmark is None or endmark['tick']!=packets[-1]['tick'] or endmark['seq']!=packets[-1]['seq']:raise Refusal('MISSING_OR_INVALID_EOS')
    rows=np.array([(j,p['time'],p['power'],p['energy']) for j,p in enumerate(packets)],dtype=float)
    return dict(rows=rows,packets=packets,footer=endmark,origin=origin,h=h,sp=sp,se=se,crc=crc)

def unwrap_steps(previous,current,max_ticks_per_segment=10):
    """Unique number of lost/delivered edges from ticks and modulo sequence."""
    delta=current['tick']-previous['tick']
    if delta<=0:raise Refusal('INVALID_TICK_ORDER')
    lo=(delta+max_ticks_per_segment-1)//max_ticks_per_segment;hi=delta
    residue=(current['seq']-previous['seq'])%65536
    first=residue+max(0,(lo-residue+65535)//65536)*65536
    if first<lo or first>hi:return None,'inconsistent'
    if first+65536<=hi:return None,'ambiguous'
    return first,'unique'

@lru_cache(maxsize=65536)
def packet_fields(blob,header_bytes):
    """Pure memoized parsing keyed by the complete actual bytes and header.

    Lost packets cannot be obtained from an index or a sender trace. A cache
    entry is usable only once its entire byte string is received or exactly
    reconstructed by FEC, and changing any byte changes the parser argument.
    """
    _,origin,h,sp,se=HEADER.unpack(header_bytes)
    item,pos=decode_packet(blob,0,origin,h,sp,se)
    if pos!=len(blob):raise Refusal('TRAILING_PACKET_BYTES')
    return (item['kind'],item['seq'],item['tick'],item['time'],item.get('power'),item.get('energy'))

def received_packet(blob,header_bytes,memoized=True):
    if memoized:kind,seq,ti,time,power,energy=packet_fields(blob,header_bytes)
    else:
        _,origin,h,sp,se=HEADER.unpack(header_bytes);item,pos=decode_packet(blob,0,origin,h,sp,se)
        if pos!=len(blob):raise Refusal('TRAILING_PACKET_BYTES')
        return item
    return dict(kind=kind,seq=seq,tick=ti,time=time,power=power,energy=energy,blob=blob)

def receive(header_bytes,payloads,endmark=None,memoized=True):
    magic,origin,h,sp,se=HEADER.unpack(header_bytes)
    if magic not in MAGICS.values() or not np.isfinite([origin,h,sp,se]).all() or min(h,sp,se)<=0:raise Refusal('INVALID_HEADER')
    packets=[]
    for blob in payloads:
        item=received_packet(blob,header_bytes,memoized)
        if item['kind']==EOS:raise Refusal('INVALID_DATAGRAM_PACKET')
        if packets and item['tick']<=packets[-1]['tick']:raise Refusal('INVALID_PACKET_ORDER')
        packets.append(item)
    adjacency=[];ambiguities=0
    for j,(aa,bb) in enumerate(zip(packets[:-1],packets[1:])):
        steps,status=unwrap_steps(aa,bb)
        if status=='inconsistent':raise Refusal('SEQUENCE_TICK_INCONSISTENCY')
        ambiguities+=status=='ambiguous'
        if steps==1:adjacency.append(j)
    terminal='unknown'
    if endmark is not None:
        expected,pos=decode_packet(endmark,0,origin,h,sp,se)
        if expected['kind']!=EOS or pos!=len(endmark):raise Refusal('INVALID_EOS_DATAGRAM')
        if packets:
            last=packets[-1]
            if expected['tick']<last['tick'] or (expected['tick']==last['tick'] and expected['seq']!=last['seq']):raise Refusal('INVALID_EOS_ORDER')
            if expected['tick']>last['tick'] and unwrap_steps(last,expected)[1]=='inconsistent':raise Refusal('INVALID_EOS_SEQUENCE')
        terminal='complete' if packets and (packets[-1]['tick'],packets[-1]['seq'])==(expected['tick'],expected['seq']) else 'erased'
    return dict(packets=packets,adjacent=adjacency,ambiguous_gaps=ambiguities,terminal=terminal)

def integer_bits(value):return struct.unpack('<Q',struct.pack('<d',float(value)))[0]

def neutral_linear_bytes(t,spans,connected=True):
    """Lossless decode/recode control: same ULEB integer field type, no new error."""
    out=bytearray(HEADER.pack(b'ULN8',float(t[0]),.5,0.,0.))
    if connected:
        points=[(int(spans[0,0]),float(spans[0,2]))]+[(int(v[1]),float(v[3])) for v in spans]
        for j,(idx,p) in enumerate(points):out+=struct.pack('<H',j%65536)+uleb(idx)+uleb(integer_bits(p))
    else:
        for j,v in enumerate(spans):
            out+=struct.pack('<H',j%65536)+uleb(int(v[0]))+uleb(int(v[1]))+uleb(integer_bits(v[2]))+uleb(integer_bits(v[3]))
    return bytes(out)
