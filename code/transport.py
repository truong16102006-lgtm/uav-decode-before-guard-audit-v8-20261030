"""Actual datagram packing, endpoint repetition and one-erasure XOR recovery."""
import struct
from functools import lru_cache
import numpy as np
from wire import *

DATA=0xd0;PARITY=0xf0

def data_frame(index,packets):return bytes([DATA])+uleb(index)+uleb(len(packets))+b''.join(packets)

@lru_cache(maxsize=8192)
def unpack_data(blob,header_bytes):
    if not blob or blob[0]!=DATA:raise Refusal('INVALID_DATA_FRAME')
    index,pos=read_uleb(blob,1);count,pos=read_uleb(blob,pos)
    _,origin,h,sp,se=HEADER.unpack(header_bytes);out=[]
    for _ in range(count):
        item,pos=decode_packet(blob,pos,origin,h,sp,se)
        if item['kind']==EOS:raise Refusal('EOS_INSIDE_DATA_FRAME')
        out.append(item['blob'])
    if pos!=len(blob):raise Refusal('TRAILING_DATA_FRAME_BYTES')
    return index,tuple(out)

def parity_frame(block_index,data):
    lengths=[len(blob) for blob in data];width=max(lengths);xor=np.zeros(width,dtype=np.uint8)
    for blob in data:xor[:len(blob)]^=np.frombuffer(blob,dtype=np.uint8)
    return bytes([PARITY])+uleb(block_index)+uleb(len(data))+b''.join(uleb(n) for n in lengths)+xor.tobytes()

def unpack_parity(blob):
    if not blob or blob[0]!=PARITY:raise Refusal('INVALID_PARITY_FRAME')
    index,pos=read_uleb(blob,1);count,pos=read_uleb(blob,pos);lengths=[]
    for _ in range(count):value,pos=read_uleb(blob,pos);lengths.append(value)
    if not lengths or max(lengths)!=len(blob)-pos:raise Refusal('INVALID_PARITY_LENGTH')
    return index,lengths,blob[pos:]

def pack_stream(decoded,m=1,protection='none',parity_k=4):
    """Return transmitted UDP application payloads in their actual order.

    UDP/IP/link overhead is outside this explicit application-byte model.
    The 36-byte header is assumed delivered separately and counted once.
    """
    if m not in (1,4,16) or protection not in ('none','repeat','xor'):raise ValueError('Unsupported transport configuration')
    if decoded['crc']!=0:raise ValueError('This erasure experiment uses independently decodable CRC-free frames; whole-stream CRC is evaluated separately')
    packets=[p['blob'] for p in decoded['packets']];data=[];members=[]
    for left in range(0,len(packets),m):
        right=min(len(packets),left+m);ids=list(range(left,right))
        if protection=='repeat' and left:ids.insert(0,left-1)
        data.append(data_frame(len(data),[packets[j] for j in ids]));members.append(ids)
    transmitted=[];kinds=[];ids=[]
    if protection=='xor':
        for left in range(0,len(data),parity_k):
            block=data[left:left+parity_k]
            for j,blob in enumerate(block):transmitted.append(blob);kinds.append('data');ids.append(left+j)
            transmitted.append(parity_frame(left//parity_k,block));kinds.append('parity');ids.append(left//parity_k)
    else:
        transmitted.extend(data);kinds.extend(['data']*len(data));ids.extend(range(len(data)))
    # EOS itself provides the datagram type. No second end tag is invented.
    transmitted.append(decoded['footer']['blob']);kinds.append('footer');ids.append(-1)
    return dict(datagrams=transmitted,kinds=kinds,indices=ids,data=data,members=members,m=m,protection=protection,parity_k=parity_k,
        transmitted_bytes=36+sum(map(len,transmitted)),data_bytes=sum(map(len,data)),
        parity_bytes=sum(len(blob) for blob,kind in zip(transmitted,kinds) if kind=='parity'),
        footer_bytes=len(transmitted[-1]),max_encoded_buffer_checkpoints=m+(1 if protection=='repeat' else 0))

def recover(transport,erased,header_bytes,verify_original=False):
    delivered={};parities={};endmark=None
    for blob,drop in zip(transport['datagrams'],erased):
        if drop:continue
        if not blob:raise Refusal('EMPTY_APPLICATION_DATAGRAM')
        if blob[0]==DATA:
            ii,_=unpack_data(blob,header_bytes)
            delivered[ii]=blob
        elif blob[0]==PARITY:
            ii,lengths,payload=unpack_parity(blob);parities[ii]=(lengths,payload)
        elif blob[0]==EOS:endmark=blob
        else:raise Refusal('INVALID_APPLICATION_DATAGRAM_KIND')
    recovered=0
    for block,(lengths,payload) in parities.items():
        start=block*transport['parity_k'];missing=[start+j for j in range(len(lengths)) if start+j not in delivered]
        if len(missing)!=1:continue
        target=missing[0];out=np.frombuffer(payload,dtype=np.uint8).copy()
        for j in range(len(lengths)):
            idx=start+j
            if idx in delivered:
                blob=delivered[idx]
                if len(blob)!=lengths[j]:raise Refusal('PARITY_MEMBER_LENGTH_MISMATCH')
                out[:len(blob)]^=np.frombuffer(blob,dtype=np.uint8)
        recovered_blob=out[:lengths[target-start]].tobytes()
        ii,packets=unpack_data(recovered_blob,header_bytes)
        if ii!=target:raise Refusal('RECOVERED_FRAME_INDEX_MISMATCH')
        if verify_original and recovered_blob!=transport['data'][target]:raise AssertionError('XOR reconstruction differs from original application bytes')
        delivered[target]=recovered_blob;recovered+=1
    unique={}
    _,origin,h,sp,se=HEADER.unpack(header_bytes)
    for idx in sorted(delivered):
        _,parts=unpack_data(delivered[idx],header_bytes)
        for blob in parts:
            kind,seq,ti,when,power,energy=packet_fields(blob,header_bytes);key=(ti,seq)
            if key in unique and unique[key]!=blob:raise Refusal('CONFLICTING_DUPLICATE_ENDPOINT')
            unique[key]=blob
    payloads=[unique[k] for k in sorted(unique)]
    result=receive(header_bytes,payloads,endmark)
    result.update(recovered_data_frames=recovered,delivered_data_frames=len(delivered),footer_delivered=endmark is not None)
    return result

def ge_mask(n,rate,rng,bad_mean=3.):
    q=1/bad_mean;alpha=rate*q/(1-rate);bad=bool(rng.random()<rate);erased=np.empty(n,dtype=bool)
    for j in range(n):
        erased[j]=bad
        bad=(rng.random()>=q) if bad else (rng.random()<alpha)
    return erased

def analytic_bernoulli(decoded,transport,rate):
    if transport['protection']!='none':raise ValueError('Closed form here is for uncoded packing only')
    n=len(decoded['packets']);frame=np.empty(n,dtype=int)
    for j,ids in enumerate(transport['members']):frame[ids]=j
    durations=np.diff(decoded['rows'][:,1]);probs=np.where(frame[:-1]==frame[1:],1-rate,(1-rate)**2)
    return float(np.dot(durations,probs)/durations.sum()),float(1-rate)
