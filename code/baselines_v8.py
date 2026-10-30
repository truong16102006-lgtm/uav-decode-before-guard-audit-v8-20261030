"""Guard-matched baselines with actual native wires and lossless ULEB recoding controls."""
import struct,math
import numpy as np
import zfpy,zstandard
from kernels import *
from wire import HEADER,uleb,integer_bits,neutral_linear_bytes,PROFILES
from encoders import metrics_dict

NATIVE=struct.Struct('<Idfd')
LINEAR_POINT=struct.Struct('<HIi')
LINEAR_SPAN=struct.Struct('<HIIii')

def native_linear_wire(t,spans,method):
    magic={'Swing':b'SWG1','SlideCore':b'SLD1','DPvertical':b'DPV1'}[method]
    parts=[HEADER.pack(magic,float(t[0]),.5,.1,0.)]
    if method=='SlideCore':
        for j,v in enumerate(spans):parts.append(LINEAR_SPAN.pack(j,int(v[0]),int(v[1]),round(v[2]/.1),round(v[3]/.1)))
    else:
        points=[(int(spans[0,0]),spans[0,2])]+[(int(v[1]),v[3]) for v in spans]
        for j,(ti,p) in enumerate(points):parts.append(LINEAR_POINT.pack(j,ti,round(p/.1)))
    return b''.join(parts)

def linear_control(t,p,e,method,iso=False):
    which={'Swing':0,'SlideCore':1,'DPvertical':2}[method]
    if iso:spans,eps,tested,m,okay=iso_guard(t,p,e,which)
    else:
        spans,okay=[swing_spans,slide_spans,dp_spans][which](t,p,24.95)
        eps=24.95;tested=1;m=linear_metrics(t,p,e,spans) if okay else (np.nan,)*4
    if not okay:return dict(status='NO_FEASIBLE_POINT_IN_0_25_CATALOGUE' if iso else 'CONSTRUCTION_REFUSAL',parameter=eps,candidates_tested=tested)
    wire=native_linear_wire(t,spans,method);neutral=neutral_linear_bytes(t,spans,method!='SlideCore')
    return dict(status='OK',parameter=float(eps),candidates_tested=int(tested),wire=wire,neutral_wire=neutral,
        encoded_bytes=len(wire),neutral_bytes=len(neutral),spans=spans,passes=bool(guard(m)),**metrics_dict(m))

def dense_spans(t,values):
    out=np.empty((len(t)-1,4));out[:,0]=np.arange(len(t)-1);out[:,1]=np.arange(1,len(t));out[:,2]=values[:-1];out[:,3]=values[1:]
    return out

def zfp_control(t,p,e,iso=False):
    candidates=[25.] if not iso else [min(25.,np.nextafter(2.**(k+1),0.)) for k in range(4,-41,-1)]
    tested=0;last=None;bucket_checks=0
    for tol in candidates:
        tested+=1;payload=zfpy.compress_numpy(np.asarray(p,dtype=np.float64),tolerance=float(tol),write_header=True)
        recovered=zfpy.decompress_numpy(payload);spans=dense_spans(t,recovered);m=linear_metrics(t,p,e,spans)
        if iso:
            # Match zfp's frexp-based exponent extraction exactly. log2 can
            # round nextafter(2**k, 0) up to k, selecting the wrong bucket.
            effective=math.ldexp(1.,math.frexp(tol)[1]-1)
            assert zfpy.header(payload)['config']['tolerance']==effective
            lower=zfpy.compress_numpy(np.asarray(p,dtype=np.float64),tolerance=effective,write_header=True)
            if lower!=payload:raise ValueError('ZFP_BUCKET_IDENTITY_NOT_VERIFIED')
            bucket_checks+=1
        last=(payload,recovered,spans,m,tol)
        if not iso or guard(m):break
    payload,recovered,spans,m,tol=last
    if iso and not guard(m):return dict(status='NO_FEASIBLE_TESTED_ACCURACY_BUCKET',candidates_tested=tested,bucket_identity_checks=bucket_checks)
    wire=HEADER.pack(b'ZFP1',float(t[0]),.5,float(tol),0.)+payload
    neutral=neutral_linear_bytes(t,spans,True)
    return dict(status='OK',wire=wire,neutral_wire=neutral,encoded_bytes=len(wire),neutral_bytes=len(neutral),
        parameter=float(tol),effective_accuracy=float(math.ldexp(1.,math.frexp(tol)[1]-1)),candidates_tested=tested,
        bucket_identity_checks=bucket_checks,spans=spans,passes=bool(guard(m)),**metrics_dict(m))

def zstd_control(t,p,e):
    raw=np.asarray(np.c_[t,p],dtype='<f8').tobytes();payload=zstandard.ZstdCompressor(level=3,threads=0,write_checksum=True).compress(raw)
    wire=HEADER.pack(b'ZST1',float(t[0]),.5,0.,0.)+payload
    actual=zstandard.ZstdDecompressor().decompress(wire[36:]);assert actual==raw
    recovered=np.frombuffer(actual,dtype='<f8').reshape(-1,2);spans=dense_spans(t,recovered[:,1]);m=linear_metrics(t,p,e,spans)
    neutral=neutral_linear_bytes(t,spans,True)
    return dict(status='OK',wire=wire,neutral_wire=neutral,encoded_bytes=len(wire),neutral_bytes=len(neutral),spans=spans,passes=bool(guard(m)),**metrics_dict(m))

def sz3_control(t,p,e,tolerance=25.):
    from pysz import sz,szConfig,szErrorBoundMode
    config=szConfig();config.errorBoundMode=szErrorBoundMode.ABS;config.absErrorBound=float(tolerance)
    original=np.asarray(p,dtype=np.float64);payload,ratio=sz.compress(original,config)
    blob=np.asarray(payload,dtype=np.uint8).tobytes()
    # dtype and shape are explicit application bytes needed by this binding.
    meta=struct.pack('<BQ',2,len(p));wire=HEADER.pack(b'SZ38',float(t[0]),.5,tolerance,0.)+meta+blob
    dtype,n=struct.unpack_from('<BQ',wire,36);assert dtype==2
    decoded,returned_config=sz.decompress(np.frombuffer(wire[45:],dtype=np.uint8).copy(),np.float64,(n,))
    spans=dense_spans(t,decoded);m=linear_metrics(t,p,e,spans);neutral=neutral_linear_bytes(t,spans,True)
    return dict(status='OK',wire=wire,neutral_wire=neutral,encoded_bytes=len(wire),neutral_bytes=len(neutral),
        parameter=tolerance,spans=spans,passes=bool(guard(m)),**metrics_dict(m))

def neutral_area_wire(t,indices,power,energy,kinds=None):
    # Mixed-decoder flags are placed within their endpoint records and really
    # decoded, rather than charging an uninterpreted trailer for them.
    parts=[HEADER.pack(b'UMX8' if kinds is not None else b'UAR8',float(t[0]),.5,0.,0.)]
    for j,(i,p,e) in enumerate(zip(indices,power,energy)):
        flag=b'' if kinds is None else bytes([int(kinds[j])])
        parts.append(flag+struct.pack('<H',j%65536)+uleb(int(i))+uleb(integer_bits(p))+uleb(integer_bits(e)))
    blob=b''.join(parts)
    from wire import read_uleb
    pos=36
    for j,(i,p,e) in enumerate(zip(indices,power,energy)):
        if kinds is not None:assert blob[pos]==int(kinds[j]);pos+=1
        assert struct.unpack_from('<H',blob,pos)[0]==j%65536;pos+=2
        ti,pos=read_uleb(blob,pos);pi,pos=read_uleb(blob,pos);ei,pos=read_uleb(blob,pos)
        assert ti==int(i) and pi==integer_bits(p) and ei==integer_bits(e)
    assert pos==len(blob)
    return blob

def native_area(t,p,e):
    """Original 24-byte uint32/time64/power32/energy64 checkpoints, now with header."""
    pp=np.asarray(p,dtype=np.float32).astype(np.float64);indices=[0];a=0;accepted=None
    for b in range(1,len(t)):
        m=segment_stats(t,p,e,a,b,pp[a],pp[b],e[a],e[b])
        if not guard(m):
            if b==a+1:return dict(status='NATIVE_ADJACENT_REFUSAL',failed_metrics=metrics_dict(m))
            indices.append(b-1);a=b-1;m=segment_stats(t,p,e,a,b,pp[a],pp[b],e[a],e[b])
            if not guard(m):return dict(status='NATIVE_RESTART_REFUSAL',failed_metrics=metrics_dict(m))
    if indices[-1]!=len(t)-1:indices.append(len(t)-1)
    parts=[HEADER.pack(b'NAT8',float(t[0]),.5,0.,0.)]
    for j,i in enumerate(indices):parts.append(NATIVE.pack(j,float(t[i]),float(pp[i]),float(e[i])))
    wire=b''.join(parts);decoded=np.array([NATIVE.unpack_from(wire,k) for k in range(36,len(wire),NATIVE.size)])
    top=[0.,0.,np.inf,0.]
    for j,(a,b) in enumerate(zip(indices[:-1],indices[1:])):
        m=segment_stats(t,p,e,a,b,decoded[j,2],decoded[j+1,2],decoded[j,3],decoded[j+1,3])
        top=[max(top[0],m[0]),max(top[1],m[1]),min(top[2],m[2]),max(top[3],m[3])]
    neutral=neutral_area_wire(t,indices,decoded[:,2],decoded[:,3])
    return dict(status='OK',wire=wire,neutral_wire=neutral,encoded_bytes=len(wire),neutral_bytes=len(neutral),indices=np.array(indices),rows=decoded,passes=bool(guard(tuple(top))),**metrics_dict(top))

def energy_aware(t,p,e,proposal='raw',linear=False):
    """Online maximal accepted prefixes with absolute-energy decoded fields.

    Swing uses an anchored feasible corridor. Slide fits a disjoint strip and
    stores both power endpoints. All emitted segments pass the same guards.
    Linear mode reports energy reset jumps rather than claiming conservation.
    """
    sp,se=PROFILES['medium'];a=0;b=1;anchor_p=round(p[0]/sp)*sp;anchor_e=round(e[0]/se)*se
    lo=-np.inf;hi=np.inf;accepted=None;spans=[];fields=[];release=0.;maxbuffer=1
    while b<len(t):
        maxbuffer=max(maxbuffer,b-a+1);dt=t[b]-t[a]
        corridor=True;pa=anchor_p;pb=float(p[b])
        if proposal=='swing':
            lower=max(lo,(p[b]-24.95-anchor_p)/dt);upper=min(hi,(p[b]+24.95-anchor_p)/dt);corridor=lower<=upper
            if corridor:
                lo=lower;hi=upper;x=t[a+1:b+1]-t[a];slope=np.dot(x,p[a+1:b+1]-anchor_p)/np.dot(x,x)
                pb=anchor_p+float(np.clip(slope,lo,hi))*dt
        elif proposal=='slide':
            x=t[a:b+1]-t[a];y=p[a:b+1];dts=t[b]-t[a:b]
            lower=max(lo,float(np.max((p[b]-p[a:b]-49.9)/dts)));upper=min(hi,float(np.min((p[b]-p[a:b]+49.9)/dts)));corridor=lower<=upper
            if corridor:
                lo=lower;hi=upper;xc=x-x.mean();slope=float(np.clip(np.dot(xc,y-y.mean())/np.dot(xc,xc),lo,hi))
                zl=float(np.max(y-24.95-slope*x));zu=float(np.min(y+24.95-slope*x));pa=float(np.clip(np.mean(y-slope*x),zl,zu));pb=pa+slope*dt
        # Construct and decode the candidate's actual integer fields before
        # admission, using the same field representation as the emitted span.
        from wire import read_uleb
        counts=(int(a),int(b),round(pa/sp),round(pb/sp),round(anchor_e/se),round(e[b]/se))
        fields_valid=True
        try:
            candidate=b''.join(uleb(v) for v in counts)
            decoded_counts=[];candidate_pos=0
            for _ in range(6):
                value,candidate_pos=read_uleb(candidate,candidate_pos);decoded_counts.append(value)
            assert candidate_pos==len(candidate)
            aa,bb,qa,qb,qe0,qe1=decoded_counts
            assert aa==a and bb==b
            pa,pb,anchor_e,eb=qa*sp,qb*sp,qe0*se,qe1*se
        except (ValueError,OverflowError):
            fields_valid=False;corridor=False
        m=segment_stats(t,p,e,a,b,pa,pb,anchor_e,eb,linear) if fields_valid else (np.inf,np.inf,-np.inf,dt)
        if dt<=5+1e-10 and corridor and guard(m):accepted=(a,b,pa,pb,anchor_e,eb,m);b+=1;continue
        if accepted is None:return dict(status='ENERGY_AWARE_ADJACENT_REFUSAL',failed_metrics=metrics_dict(m))
        spans.append(accepted);release=max(release,t[b]-t[a]);a=accepted[1];anchor_p=accepted[3];anchor_e=accepted[5]
        accepted=None;lo=-np.inf;hi=np.inf
    if accepted is not None:spans.append(accepted);release=max(release,t[-1]-t[a])
    header_magic=b'ELR8' if linear else b'ESL8' if proposal=='slide' else b'ESW8' if proposal=='swing' else b'EAR8'
    parts=[HEADER.pack(header_magic,float(t[0]),.5,sp,se)];top=[0.,0.,np.inf,0.];reset=0.
    for j,(a,b,pa,pb,ea,eb,m) in enumerate(spans):
        # Method-specific field counts are retained; same ULEB count encoding.
        parts.append(struct.pack('<H',j%65536)+uleb(a)+uleb(b)+uleb(round(pa/sp))+uleb(round(pb/sp))+uleb(round(ea/se))+uleb(round(eb/se)))
        top=[max(top[0],m[0]),max(top[1],m[1]),min(top[2],m[2]),max(top[3],m[3])]
        reset=max(reset,abs(ea+(t[b]-t[a])*(pa+pb)/7200-eb)) if linear else reset
    wire=b''.join(parts)
    # Decode every count from the produced segment wire before final measurement.
    from wire import read_uleb
    pos=36;decoded=[]
    while pos<len(wire):
        seq=struct.unpack_from('<H',wire,pos)[0];pos+=2;vv=[]
        for _ in range(6):v,pos=read_uleb(wire,pos);vv.append(v)
        aa,bb,pa,pb,ea,eb=vv;decoded.append((aa,bb,pa*sp,pb*sp,ea*se,eb*se))
    top=[0.,0.,np.inf,0.]
    for aa,bb,pa,pb,ea,eb in decoded:
        m=segment_stats(t,p,e,aa,bb,pa,pb,ea,eb,linear)
        top=[max(top[0],m[0]),max(top[1],m[1]),min(top[2],m[2]),max(top[3],m[3])]
    neutral=[HEADER.pack(b'USA8',float(t[0]),.5,0.,0.)]
    for j,(aa,bb,pa,pb,ea,eb) in enumerate(decoded):
        neutral.append(struct.pack('<H',j%65536)+uleb(aa)+uleb(bb)+b''.join(uleb(integer_bits(v)) for v in [pa,pb,ea,eb]))
    neutral=b''.join(neutral)
    return dict(status='OK',wire=wire,encoded_bytes=len(wire),spans=np.asarray(decoded),passes=bool(guard(tuple(top))),
        neutral_wire=neutral,neutral_bytes=len(neutral),energy_reset_jump_Wh=reset,integral_conservative=not linear,release_s=release,max_buffer=maxbuffer,**metrics_dict(top))
