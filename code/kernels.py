"""Compiled exact-extremum kernels; no fastmath and no physical-sensor certificate."""
import math
import numpy as np
from numba import njit

@njit(cache=True,fastmath=False)
def cumulative_energy(t,p):
    e=np.zeros(len(t));joules=0.
    for j in range(1,len(t)):
        joules+=(p[j-1]+p[j])*(t[j]-t[j-1])/2
        e[j]=joules/3600
    return e

@njit(cache=True,fastmath=False)
def segment_stats(t,p,e,a,b,pa,pb,ea,eb,linear=False):
    """Return max|Q-P|, max|Ehat-E|, min Q and duration on [a,b]."""
    D=t[b]-t[a]
    if D<=0:return np.inf,np.inf,-np.inf,D
    correction=3600*(eb-ea)/D-(pa+pb)/2
    c0=pa;c1=pb-pa if linear else pb-pa+6*correction;c2=0. if linear else -6*correction
    minimum=min(c0,c0+c1+c2)
    if abs(c2)>1e-15:
        u=-c1/(2*c2)
        if 0<u<1:minimum=min(minimum,c0+c1*u+c2*u*u)
    ep=0.;ee=0.
    for j in range(a,b+1):
        u=(t[j]-t[a])/D
        q=c0+c1*u+c2*u*u
        eh=ea+D*(c0*u+c1*u*u/2+c2*u*u*u/3)/3600
        ep=max(ep,abs(q-p[j]));ee=max(ee,abs(eh-e[j]))
        if j==b:continue
        u1=(t[j+1]-t[a])/D;slope=(p[j+1]-p[j])/(u1-u)
        if abs(c2)>1e-15:
            z=(slope-c1)/(2*c2)
            if u<z<u1:
                qz=c0+c1*z+c2*z*z;ref=p[j]+slope*(z-u);ep=max(ep,abs(qz-ref))
        bb=c1-slope;cc=c0-p[j]+slope*u
        roots=np.empty(2);count=0
        if abs(c2)<=1e-15:
            if abs(bb)>1e-15:roots[0]=-cc/bb;count=1
        else:
            discriminant=bb*bb-4*c2*cc
            if discriminant>=0:
                sq=math.sqrt(discriminant);zq=-.5*(bb+math.copysign(sq,bb))
                roots[0]=zq/c2;roots[1]=cc/zq if zq!=0 else 0.;count=2
        for k in range(count):
            z=roots[k]
            if u<z<u1:
                local=z-u;ref=e[j]+D*(p[j]*local+.5*slope*local*local)/3600
                eh=ea+D*(c0*z+c1*z*z/2+c2*z*z*z/3)/3600
                ee=max(ee,abs(eh-ref))
    return ep,ee,minimum,D

@njit(cache=True,fastmath=False)
def guard(stats,power=25.,area=.001,duration=5.):
    return stats[0]<=power+1e-8 and stats[1]<=area+1e-12 and stats[2]>=-1e-8 and 0<stats[3]<=duration+1e-10

@njit(cache=True,fastmath=False)
def power_extrema(t,p,a,b,pa,pb,ea,eb,linear=False):
    D=t[b]-t[a];c=3600*(eb-ea)/D-(pa+pb)/2
    c1=pb-pa if linear else pb-pa+6*c;c2=0. if linear else -6*c;value=0.
    for j in range(a,b+1):
        u=(t[j]-t[a])/D;value=max(value,abs(pa+c1*u+c2*u*u-p[j]))
        if j==b:continue
        v=(t[j+1]-t[a])/D;slope=(p[j+1]-p[j])/(v-u)
        if abs(c2)>1e-15:
            root=(slope-c1)/(2*c2)
            if u<root<v:value=max(value,abs(pa+c1*root+c2*root*root-p[j]-slope*(root-u)))
    return value

@njit(cache=True,fastmath=False)
def energy_extrema(t,p,e,a,b,pa,pb,ea,eb,linear=False):
    D=t[b]-t[a];c=3600*(eb-ea)/D-(pa+pb)/2
    c1=pb-pa if linear else pb-pa+6*c;c2=0. if linear else -6*c;value=0.
    for j in range(a,b+1):
        u=(t[j]-t[a])/D;eh=ea+D*(pa*u+c1*u*u/2+c2*u*u*u/3)/3600;value=max(value,abs(eh-e[j]))
        if j==b:continue
        v=(t[j+1]-t[a])/D;slope=(p[j+1]-p[j])/(v-u);bb=c1-slope;cc=pa-p[j]+slope*u
        roots=np.empty(2);count=0
        if abs(c2)<=1e-15:
            if abs(bb)>1e-15:roots[0]=-cc/bb;count=1
        else:
            disc=bb*bb-4*c2*cc
            if disc>=0:
                sq=math.sqrt(disc);zq=-.5*(bb+math.copysign(sq,bb))
                roots[0]=zq/c2;roots[1]=cc/zq if zq else 0.;count=2
        for k in range(count):
            z=roots[k]
            if u<z<v:
                local=z-u;reference=e[j]+D*(p[j]*local+.5*slope*local*local)/3600
                eh=ea+D*(pa*z+c1*z*z/2+c2*z*z*z/3)/3600;value=max(value,abs(eh-reference))
    return value

@njit(cache=True,fastmath=False)
def shape_minimum(pa,pb,ea,eb,D,linear=False):
    c=3600*(eb-ea)/D-(pa+pb)/2;c1=pb-pa if linear else pb-pa+6*c;c2=0. if linear else -6*c
    value=min(pa,pa+c1+c2)
    if abs(c2)>1e-15:
        u=-c1/(2*c2)
        if 0<u<1:value=min(value,pa+c1*u+c2*u*u)
    return value

@njit(cache=True,fastmath=False)
def var_width(n):
    count=1
    while n>=128:n//=128;count+=1
    return count

@njit(cache=True,fastmath=False)
def canonical_nodes(t,p,e,sp,se,h=.5,origin=np.nan):
    n=len(t);rows=np.empty((n,3));cost=np.empty(n,np.int64)
    if math.isnan(origin):origin=t[0]
    for j in range(n):
        # This compiled graph uses signed int64 internal costs/counts. The
        # general wire supports U64, but do not silently cast a larger field.
        if not (0<=(t[j]-origin)/h<2.**63 and 0<=p[j]/sp<2.**63 and 0<=e[j]/se<2.**63):
            raise ValueError('GRAPH_INTERNAL_INT64_RANGE')
        tick=int(round((t[j]-origin)/h));pc=int(round(p[j]/sp));ec=int(round(e[j]/se))
        rows[j,0]=origin+tick*h;rows[j,1]=pc*sp;rows[j,2]=ec*se
        cost[j]=3+var_width(tick)+var_width(pc)+var_width(ec)
    return rows,cost

@njit(cache=True,fastmath=False)
def byte_oracle(t,p,e,nodes,cost,power=25.,area=.001,steps=10):
    """Weighted fixed-node DAG; at most steps predecessors per reachable node."""
    n=len(t);best=np.full(n,np.inf);previous=np.full(n,-1,np.int64);best[0]=cost[0]
    for b in range(1,n):
        for a in range(max(0,b-steps),b):
            if not math.isfinite(best[a]):continue
            m=segment_stats(t,p,e,a,b,nodes[a,1],nodes[b,1],nodes[a,2],nodes[b,2])
            candidate=best[a]+cost[b]
            if guard(m,power,area) and candidate<best[b]:best[b]=candidate;previous[b]=a
    if not math.isfinite(best[-1]):return np.empty(0,np.int64),np.inf
    path=np.empty(n,np.int64);k=0;at=n-1
    while at>=0:
        path[k]=at;k+=1;at=previous[at]
    return path[:k][::-1].copy(),best[-1]

@njit(cache=True,fastmath=False)
def first_horizon_edge(t,p,e,nodes,cost,power=25.,area=.001,steps=10):
    width=len(t);best=np.full(width,np.inf);first=np.full(width,-1,np.int64);best[0]=0.;checks=0
    for b in range(1,width):
        for a in range(max(0,b-steps),b):
            if not math.isfinite(best[a]):continue
            m=segment_stats(t,p,e,a,b,nodes[a,1],nodes[b,1],nodes[a,2],nodes[b,2]);checks+=1
            value=best[a]+cost[b];edge=b if a==0 else first[a]
            if guard(m,power,area) and (value<best[b] or (value==best[b] and edge>first[b])):
                best[b]=value;first[b]=edge
    return first[-1],checks

@njit(cache=True,fastmath=False)
def finite_horizon(t,p,e,nodes,cost,extra,power=25.,area=.001,steps=10):
    """Commit the first byte-optimal edge in the observed bounded horizon."""
    n=len(t);path=np.empty(n,np.int64);path[0]=0;used=1;left=0;maxbuffer=1;delay=0.;checks=0
    while left<n-1:
        end=min(n-1,left+steps+extra);width=end-left+1
        maxbuffer=max(maxbuffer,width);delay=max(delay,t[end]-t[left])
        best=np.full(width,np.inf);first=np.full(width,-1,np.int64);best[0]=0
        for local in range(1,width):
            b=left+local
            for start in range(max(0,local-steps),local):
                if not math.isfinite(best[start]):continue
                a=left+start;m=segment_stats(t,p,e,a,b,nodes[a,1],nodes[b,1],nodes[a,2],nodes[b,2])
                checks+=1
                value=best[start]+cost[b];edge=b if start==0 else first[start]
                if guard(m,power,area) and (value<best[local] or (value==best[local] and edge>first[local])):
                    best[local]=value;first[local]=edge
        if first[-1]<0:return path[:used],False,maxbuffer,delay,checks
        left=first[-1];path[used]=left;used+=1
    return path[:used],True,maxbuffer,delay,checks

@njit(cache=True,fastmath=False)
def linear_metrics(t,p,e,spans):
    ep=0.;ee=0.;minimum=np.inf;duration=0.;carry=0.
    for j in range(len(spans)):
        a=int(spans[j,0]);b=int(spans[j,1]);pa=spans[j,2];pb=spans[j,3]
        m=segment_stats(t,p,e,a,b,pa,pb,carry,0.,True)
        ep=max(ep,m[0]);ee=max(ee,m[1]);minimum=min(minimum,m[2]);duration=max(duration,m[3])
        carry+=(t[b]-t[a])*(pa+pb)/7200
    return ep,ee,minimum,duration

@njit(cache=True,fastmath=False)
def swing_spans(t,p,eps,duration=5.,quantum=.1):
    spans=np.empty((len(t),4));count=0;a=0;b=1;start=round(p[0]/quantum)*quantum;lo=-np.inf;hi=np.inf;last=-1;lastp=0.
    while b<len(t):
        D=t[b]-t[a];lower=max(lo,(p[b]-eps-start)/D);upper=min(hi,(p[b]+eps-start)/D)
        if D<=duration+1e-10 and lower<=upper:
            lo=lower;hi=upper;num=0.;den=0.
            for j in range(a+1,b+1):
                x=t[j]-t[a];num+=x*(p[j]-start);den+=x*x
            slope=min(hi,max(lo,num/den));last=b;lastp=start+slope*D;b+=1
        else:
            if last<0:return spans[:count],False
            end=round(lastp/quantum)*quantum;spans[count]=np.array([a,last,start,end]);count+=1
            a=last;start=end;lo=-np.inf;hi=np.inf;last=-1
    if a<len(t)-1:
        end=round(lastp/quantum)*quantum;spans[count]=np.array([a,last,start,end]);count+=1
    return spans[:count],True

@njit(cache=True,fastmath=False)
def slide_spans(t,p,eps,duration=5.,quantum=.1):
    spans=np.empty((len(t),4));count=0;a=0;b=1;lo=-np.inf;hi=np.inf;last=-1;pa=0.;pb=0.
    while b<len(t):
        lower=lo;upper=hi
        for j in range(a,b):
            dt=t[b]-t[j];lower=max(lower,(p[b]-p[j]-2*eps)/dt);upper=min(upper,(p[b]-p[j]+2*eps)/dt)
        if t[b]-t[a]<=duration+1e-10 and lower<=upper:
            lo=lower;hi=upper;xm=0.;ym=0.;n=b-a+1
            for j in range(a,b+1):xm+=t[j]-t[a];ym+=p[j]
            xm/=n;ym/=n;num=0.;den=0.
            for j in range(a,b+1):
                x=t[j]-t[a]-xm;num+=x*(p[j]-ym);den+=x*x
            slope=min(hi,max(lo,num/den));zl=-np.inf;zu=np.inf;zm=0.
            for j in range(a,b+1):
                v=p[j]-slope*(t[j]-t[a]);zl=max(zl,v-eps);zu=min(zu,v+eps);zm+=v
            intercept=min(zu,max(zl,zm/n));last=b;pa=intercept;pb=intercept+slope*(t[b]-t[a]);b+=1
        else:
            if last<0:return spans[:count],False
            spans[count]=np.array([a,last,round(pa/quantum)*quantum,round(pb/quantum)*quantum]);count+=1
            a=last;lo=-np.inf;hi=np.inf;last=-1
    if a<len(t)-1:spans[count]=np.array([a,last,round(pa/quantum)*quantum,round(pb/quantum)*quantum]);count+=1
    return spans[:count],True

@njit(cache=True,fastmath=False)
def dp_spans(t,p,eps,duration=5.,quantum=.1):
    n=len(t);keep=np.zeros(n,np.bool_);keep[0]=True;keep[-1]=True
    stack=np.empty((2*n,2),np.int64);stack[0,0]=0;stack[0,1]=n-1;top=1
    while top:
        top-=1;a=stack[top,0];b=stack[top,1]
        if b-a<2:continue
        err=-1.;split=-1
        for j in range(a+1,b):
            u=(t[j]-t[a])/(t[b]-t[a]);v=abs(p[j]-(p[a]+(p[b]-p[a])*u))
            if v>err:err=v;split=j
        if err<=eps:
            if t[b]-t[a]<=duration+1e-10:continue
            split=min(b-1,a+int(round(duration/(t[1]-t[0]))))
        keep[split]=True;stack[top,0]=a;stack[top,1]=split;stack[top+1,0]=split;stack[top+1,1]=b;top+=2
    spans=np.empty((n,4));count=0;last=0
    for j in range(1,n):
        if keep[j]:spans[count]=np.array([last,j,round(p[last]/quantum)*quantum,round(p[j]/quantum)*quantum]);count+=1;last=j
    return spans[:count],True

@njit(cache=True,fastmath=False)
def iso_guard(t,p,e,method,power=25.,area=.001):
    """Largest passing entry in the declared .01-W finite catalogue, not R."""
    attempted=0
    for tick in range(2500,-1,-1):
        eps=tick*.01;attempted+=1
        if method==0:spans,okay=swing_spans(t,p,eps)
        elif method==1:spans,okay=slide_spans(t,p,eps)
        else:spans,okay=dp_spans(t,p,eps)
        if not okay:continue
        m=linear_metrics(t,p,e,spans)
        if guard(m,power,area):return spans,eps,attempted,m,True
    return np.empty((0,4)),np.nan,attempted,(np.nan,np.nan,np.nan,np.nan),False
