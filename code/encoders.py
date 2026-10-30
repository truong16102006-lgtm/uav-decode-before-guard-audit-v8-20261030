"""Bounded push encoder with strict, neighboring-rounding and guarded escape modes."""
import math,zlib,binascii
import numpy as np
from kernels import cumulative_energy,segment_stats,guard,canonical_nodes,byte_oracle,finite_horizon,first_horizon_edge
from wire import *

class StreamRefusal(Refusal):
    """Failure plus a committed prefix chunk that the caller must retain."""
    def __init__(self,message,emitted=b''):
        super().__init__(message);self.emitted=emitted

def counts(p,e,sp,se):
    x=p/sp;y=e/se
    if not np.isfinite([x,y]).all():raise Refusal('OVERFLOW_COUNTS')
    pc=round(x);ec=round(y)
    if not 0<=pc<2**64 or not 0<=ec<2**64:raise Refusal('OVERFLOW_UINT64')
    return pc,ec

def metrics_dict(m):return dict(power_max_W=float(m[0]),energy_max_Wh=float(m[1]),minimum_power_W=float(m[2]),max_segment_s=float(m[3]))

def failed_guards(m,power=25.,area=.001,duration=5.):
    out=[]
    if m[3]<=0:out.append('clock')
    if m[3]>duration+1e-10:out.append('duration')
    if m[0]>power+1e-8:out.append('power')
    if m[1]>area+1e-12:out.append('energy')
    if m[2]<-1e-8:out.append('nonnegativity')
    return out

class StreamingEncoder:
    """Owns at most floor(L/h)+2 raw knots; caller owns emitted chunks."""
    def __init__(self,profile='medium',search=False,escape_enabled=False,h=.5,power=25.,area=.001,duration=5.,crc=0):
        self.sp,self.se=PROFILES[profile];self.h=h;self.power=power;self.area=area;self.duration=duration
        self.search=search;self.escape_enabled=escape_enabled;self.crc_bits=crc;self.crc_state=0xffff if crc==16 else 0
        self.origin=None;self.previous=None;self.total_J=0.;self.buffer=[];self.anchor=None;self.seq=0;self.accepted=None
        self.max_buffer=0;self.release_s=0.;self.bytes_emitted=0;self.segments=0;self.escapes=0;self.guard_calls=0;self.rounding_altered=0
        self.minimum=np.inf;self.max_power=0.;self.max_energy=0.;self.max_duration=0.;self.first_failure=None;self.last_failure=None;self.finished=False

    def counted(self,blob):
        if self.crc_bits==32:self.crc_state=zlib.crc32(blob,self.crc_state)
        elif self.crc_bits==16:self.crc_state=binascii.crc_hqx(blob,self.crc_state)
        self.bytes_emitted+=len(blob);return blob

    def candidate(self,row):
        time,p,e=row;ti=tick(time,self.origin,self.h)
        if not np.isfinite([p,e]).all():raise Refusal('NONFINITE_FIELD')
        pc,ec=counts(p,e,self.sp,self.se)
        if not self.search:return [(pc,ec)]
        pp=sorted(set([math.floor(p/self.sp),math.ceil(p/self.sp),pc-1,pc,pc+1]))
        ee=sorted(set([math.floor(e/self.se),math.ceil(e/self.se),ec-1,ec,ec+1]))
        return [(pi,ei) for pi in pp for ei in ee if 0<=pi<2**64 and 0<=ei<2**64]

    def propose(self):
        row=self.buffer[-1];D=row[0]-self.anchor['time']
        if D>self.duration+1e-10:return None,dict(first='duration',all=['duration'])
        t,p,e=np.asarray(self.buffer).T;best=None;bestkey=None;nearest_metrics=None;errors=[]
        try:nearest=counts(row[1],row[2],self.sp,self.se);candidates=self.candidate(row)
        except Refusal as ex:return None,dict(first='overflow',all=[str(ex)])
        for pc,ec in candidates:
            try:
                blob=normal(self.seq,tick(row[0],self.origin,self.h),pc,ec)
                decoded,pos=decode_packet(blob,0,self.origin,self.h,self.sp,self.se)
                if pos!=len(blob):raise Refusal('INTERNAL_PACKET_FRAMING')
            except Refusal as ex:errors.append(str(ex));continue
            m=segment_stats(t,p,e,0,len(t)-1,self.anchor['power'],decoded['power'],self.anchor['energy'],decoded['energy'])
            self.guard_calls+=1
            if (pc,ec)==nearest:nearest_metrics=m
            if not guard(m,self.power,self.area,self.duration):continue
            key=(len(blob),m[1],m[0],abs(pc-row[1]/self.sp)+abs(ec-row[2]/self.se),pc,ec)
            if bestkey is None or key<bestkey:bestkey=key;best=(blob,decoded,m,(pc,ec)!=nearest)
        if best is not None:return best,None
        if nearest_metrics is not None:
            failed=failed_guards(nearest_metrics,self.power,self.area,self.duration)
            return None,dict(first=failed[0] if failed else 'rounding_candidates',all=failed,**metrics_dict(nearest_metrics))
        return None,dict(first='overflow' if any('OVERFLOW' in s for s in errors) else 'clock',all=errors)

    def emit(self,value):
        blob,decoded,m,changed=value
        self.anchor=decoded;self.seq+=1;self.segments+=1;self.escapes+=decoded['kind']==ESCAPE
        self.rounding_altered+=changed;self.max_power=max(self.max_power,m[0]);self.max_energy=max(self.max_energy,m[1])
        self.minimum=min(self.minimum,m[2]);self.max_duration=max(self.max_duration,m[3])
        return self.counted(blob)

    def adjacent_escape(self):
        t,p,e=np.asarray(self.buffer).T
        pb=float(p[-1]);D=float(t[-1]-self.anchor['time'])
        eb=self.anchor['energy']+D*(self.anchor['power']+pb)/7200
        blob=escape(self.seq,tick(float(t[-1]),self.origin,self.h),pb,eb)
        decoded,pos=decode_packet(blob,0,self.origin,self.h,self.sp,self.se)
        m=segment_stats(t,p,e,0,len(t)-1,self.anchor['power'],decoded['power'],self.anchor['energy'],decoded['energy'],True)
        self.guard_calls+=1
        if not guard(m,self.power,self.area,self.duration):return None,failed_guards(m,self.power,self.area,self.duration)
        return (blob,decoded,m,False),None

    def push(self,t,p):
        if self.finished:raise Refusal('PUSH_AFTER_FINISH')
        t=float(t);p=float(p)
        if not np.isfinite([t,p]).all() or p<0:raise Refusal('INVALID_REFERENCE_FIELD')
        if self.origin is None:self.origin=t
        if self.previous is not None:
            if t-self.previous[0]!=self.h:raise Refusal('CLOCK_NONUNIFORM_TICK')
            self.total_J+=(self.previous[1]+p)*(t-self.previous[0])/2
        row=(t,p,self.total_J/3600);self.previous=(t,p);self.buffer.append(row);self.max_buffer=max(self.max_buffer,len(self.buffer))
        if self.anchor is None:
            pc,ec=counts(p,0.,self.sp,self.se);blob=normal(0,0,pc,ec);decoded,pos=decode_packet(blob,0,self.origin,self.h,self.sp,self.se)
            if abs(decoded['power']-p)>self.power+1e-8:raise Refusal('INITIAL_POWER_BUDGET')
            self.anchor=decoded;self.seq=1
            return self.counted(header(self.origin,self.h,self.sp,self.se,self.crc_bits)+blob)
        good,diagnosis=self.propose()
        if good is not None:self.accepted=good;return b''
        out=b''
        if len(self.buffer)>2:
            self.release_s=max(self.release_s,t-self.buffer[0][0]);out=self.emit(self.accepted)
            self.buffer=self.buffer[-2:];self.accepted=None;good,diagnosis=self.propose()
            if good is not None:self.accepted=good;return out
        self.last_failure=dict(time=t,exposure_s=t-self.origin,raw_endpoint_power=p,raw_min_power=min(r[1] for r in self.buffer),**diagnosis)
        if self.first_failure is None:self.first_failure=self.last_failure.copy()
        if self.escape_enabled:
            escaped,failed=self.adjacent_escape()
            if escaped is not None:
                self.release_s=max(self.release_s,t-self.buffer[0][0]);out+=self.emit(escaped)
                self.buffer=self.buffer[-1:];self.accepted=None;return out
            self.last_failure['escape_failed_guards']=failed
        raise StreamRefusal('ADJACENT_'+str(diagnosis['first']).upper(),out)

    def finish(self):
        if self.finished:raise Refusal('DUPLICATE_FINISH')
        if self.anchor is None or (self.seq==1 and len(self.buffer)==1):raise Refusal('INSUFFICIENT_REFERENCE')
        out=b''
        if len(self.buffer)>=2:
            self.release_s=max(self.release_s,self.buffer[-1][0]-self.buffer[0][0]);out=self.emit(self.accepted)
        out+=self.counted(footer(self.seq-1,self.anchor['tick']))
        tail=struct.pack('<I',self.crc_state&0xffffffff) if self.crc_bits==32 else struct.pack('<H',self.crc_state) if self.crc_bits==16 else b''
        self.bytes_emitted+=len(tail);self.finished=True;return out+tail

    def summary(self):
        return dict(encoded_bytes=self.bytes_emitted,checkpoints=self.seq,segments=self.segments,escape_segments=self.escapes,
            max_buffer=self.max_buffer,release_s=self.release_s,guard_calls=self.guard_calls,rounding_altered_segments=self.rounding_altered,
            power_max_W=float(self.max_power),energy_max_Wh=float(self.max_energy),minimum_power_W=float(self.minimum),max_segment_s=float(self.max_duration))

class HorizonEncoder(StreamingEncoder):
    """Streaming finite-horizon byte planner, optionally with local escape fallback."""
    def __init__(self,extra=2,**kwargs):
        super().__init__(**kwargs)
        if extra not in (2,4):raise ValueError('Supported extra horizons are 2 and 4')
        self.extra=extra;self.steps=int(round(self.duration/self.h));self.window=self.steps+extra+1

    def planned(self):
        t,p,e=np.asarray(self.buffer).T
        nodes,cost=canonical_nodes(t,p,e,self.sp,self.se,self.h,self.origin)
        # A prior escape is an actual emitted anchor, not a re-quantized raw node.
        nodes[0,1]=self.anchor['power'];nodes[0,2]=self.anchor['energy']
        at,checks=first_horizon_edge(t,p,e,nodes,cost,self.power,self.area,self.steps)
        self.guard_calls+=checks
        if at<1:return None,None
        at=int(at);row=self.buffer[at];pc,ec=counts(row[1],row[2],self.sp,self.se)
        blob=normal(self.seq,tick(row[0],self.origin,self.h),pc,ec)
        decoded,pos=decode_packet(blob,0,self.origin,self.h,self.sp,self.se)
        m=segment_stats(t,p,e,0,at,self.anchor['power'],decoded['power'],self.anchor['energy'],decoded['energy'])
        self.guard_calls+=1
        if not guard(m,self.power,self.area,self.duration):raise Refusal('HORIZON_DECODED_GUARD_FAILURE')
        return (blob,decoded,m,False),at

    def commit(self):
        value,at=self.planned();observed=self.buffer[-1][0]
        if value is not None:
            self.release_s=max(self.release_s,observed-self.buffer[0][0]);out=self.emit(value);self.buffer=self.buffer[at:];return out
        saved=self.buffer;self.buffer=saved[:2]
        nearest,diagnosis=self.propose()
        self.last_failure=dict(time=saved[1][0],observed_time=observed,exposure_s=observed-self.origin,
            first='horizon_path',all=['horizon_path'] if diagnosis is None else diagnosis['all'],raw_endpoint_power=saved[1][1])
        if self.first_failure is None:self.first_failure=self.last_failure.copy()
        if self.escape_enabled:
            value,failed=self.adjacent_escape()
            if value is not None:
                self.release_s=max(self.release_s,observed-saved[0][0]);out=self.emit(value);self.buffer=saved[1:];return out
            self.last_failure['escape_failed_guards']=failed
        self.buffer=saved;raise StreamRefusal('HORIZON_NO_FEASIBLE_OBSERVED_PATH')

    def push(self,t,p):
        if self.anchor is None:return super().push(t,p)
        if self.finished:raise Refusal('PUSH_AFTER_FINISH')
        t=float(t);p=float(p)
        if not np.isfinite([t,p]).all() or p<0:raise Refusal('INVALID_REFERENCE_FIELD')
        if t-self.previous[0]!=self.h:raise Refusal('CLOCK_NONUNIFORM_TICK')
        self.total_J+=(self.previous[1]+p)*(t-self.previous[0])/2
        self.buffer.append((t,p,self.total_J/3600));self.previous=(t,p);self.max_buffer=max(self.max_buffer,len(self.buffer))
        return self.commit() if len(self.buffer)>=self.window else b''

    def finish(self):
        out=b''
        try:
            while len(self.buffer)>1:out+=self.commit()
        except StreamRefusal as e:raise StreamRefusal(str(e),out+e.emitted)
        return out+super().finish()

def encode(t,p,horizon=0,**kwargs):
    obj=HorizonEncoder(extra=horizon,**kwargs) if horizon else StreamingEncoder(**kwargs);chunks=[]
    try:
        for ti,pi in zip(t,p):chunks.append(obj.push(ti,pi))
        chunks.append(obj.finish());wire=b''.join(chunks);decoded=decode(wire)
        assert len(wire)==obj.bytes_emitted
        return dict(status='OK',wire=wire,decoded=decoded,encoder=obj,**obj.summary())
    except Refusal as e:
        # Some bytes may already have been emitted inside a push that then
        # refuses its restart; obj.bytes_emitted includes those real bytes.
        if isinstance(e,StreamRefusal):chunks.append(e.emitted)
        return dict(status=str(e),wire=b''.join(chunks),encoder=obj,first_failure=obj.first_failure,last_failure=obj.last_failure,
                    partial_emitted_bytes=obj.bytes_emitted,**obj.summary())

def measure_decoded(t,p,e,decoded):
    top=[0.,0.,np.inf,0.];rows=decoded['rows'];closure=0.
    for j,(aa,bb) in enumerate(zip(rows[:-1],rows[1:])):
        a=int(np.searchsorted(t,aa[1]));b=int(np.searchsorted(t,bb[1]));linear=decoded['packets'][j+1]['kind']==ESCAPE
        m=segment_stats(t,p,e,a,b,aa[2],bb[2],aa[3],bb[3],linear)
        top=[max(top[0],m[0]),max(top[1],m[1]),min(top[2],m[2]),max(top[3],m[3])]
        if linear:closure=max(closure,abs(aa[3]+(bb[1]-aa[1])*(aa[2]+bb[2])/7200-bb[3]))
    return metrics_dict(top)|dict(escape_linear_closure_Wh=closure,passes=bool(guard(tuple(top))))

def path_wire(t,p,e,path,profile='medium',crc=0):
    sp,se=PROFILES[profile];parts=[header(float(t[0]),.5,sp,se,crc)]
    for j,i in enumerate(path):parts.append(normal(j,tick(float(t[i]),float(t[0]),.5),round(float(p[i])/sp),round(float(e[i])/se)))
    parts.append(footer(len(path)-1,tick(float(t[path[-1]]),float(t[0]),.5)))
    out=b''.join(parts);return out+checksum(out,crc)
