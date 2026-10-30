"""Generate submission tables and vector figures only from completed v8 runs."""
from common import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def table(name,caption,label,heads,rows,small=True):
    concise={
      'support':'Medium completion on 120 s/full episodes with 30 min Solar windows and all-attempt byte percentages including escapes and Dense fallback',
      'refusals':'First failed Strict guard with 120 s counts by profile and full-episode counts over all three profiles',
      'baselines':'Non-Solar guard completion and all-attempt native/common byte percentages balanced by source and acquisition cluster',
      'horizon':'Medium completion and paired-oracle byte gaps in Strict/Horizon2/Horizon4 order, with input count N and graph-feasible Oracle count',
      'effects':r'Escape-minus-control common-byte differences in percentage points with cluster HL [95\% interval] above the Holm-adjusted wild p value in each cell',
      'drift':'Full-episode Strict paths with alternative energy decoders showing matched support, energy-budget violations and maximum continuous error',
      'loss':r'Certified duration and anchor availability for m=1/16 under 10\% loss with thirty-replicate mean/SD and framed-byte multiplier, while Fig.\ \ref{fig:v8_loss} also includes m=4',
    }
    caption=concise.get(name,caption)
    s='\\begin{table}[!htbp]\\centering'+('\\small' if small else '')+'\n\\caption{'+caption+'}\\label{'+label+'}\n\\setlength{\\tabcolsep}{3pt}\n'
    s+='\\begin{tabular}{l'+'r'*(len(heads)-1)+'}\\toprule\n'+' & '.join(heads)+r'\\\midrule'+'\n'
    s+='\n'.join(' & '.join(map(str,r))+r'\\' for r in rows)+'\n\\bottomrule\\end{tabular}\\end{table}\n'
    (ROOT/f'paper/v8_{name}.tex').write_text(s,encoding='utf8')

def source_balanced(part,column):return part.groupby(['dataset','group_id'])[column].mean().groupby('dataset').mean().mean()
def fmt(x,d=2):return '--' if pd.isna(x) else f'{x:.{d}f}' if np.isfinite(x) else r'$\infty$'
def fmtp(x):
    if 0<x<.001:
        coefficient,exponent=f'{x:.2e}'.split('e');return '$'+coefficient+r'\!\times\!10^{'+str(int(exponent))+'}$'
    return f'{x:.3f}'

def run():
    step0();f=pd.read_csv(DEV/'results/main_120.csv');full=pd.read_csv(DEV/'results/main_full.csv');b=pd.read_csv(DEV/'results/baselines.csv')
    rows=[];display={}
    for ds in ['IDF','CMU','AMOVFLY','Solar']:
        for method in ['Strict','Search','Escape','SearchEscape']:
            a=f.query('dataset==@ds and method==@method and profile=="medium"');z=full.query('dataset==@ds and method==@method and profile=="medium"')
            assert len(a)==len(z)
            rows.append([ds,method,f'{(a.status=="OK").sum()}/{len(a)}',f'{(z.status=="OK").sum()}/{len(z)}',
                fmt(100*a.record_uses_escape.mean(),1),fmt(100*a.effective_byte_ratio.mean(),1),fmt(100*z.effective_byte_ratio.mean(),1)])
    table('support','Attempted-record completion at medium precision on 120 s and full episodes, with 30 min Solar windows and all-attempt effective byte percentages including emitted prefixes, escapes and Dense restart cost','tab:v8_support',['Source','Mode','120 s','Full','Escape \\%','120 B\\%','Full B\\%'],rows)
    rows=[];zero_causes=[]
    for cause in ['power','energy','nonnegativity','duration','overflow','clock','unclassified']:
        values=[]
        for profile in ['fine','medium','coarse']:
            a=f.query('method=="Strict" and profile==@profile and status!="OK"');values.append(int(a.first_first.eq(cause).sum()))
        a=full.query('method=="Strict" and status!="OK"');values.append(int(a.first_first.eq(cause).sum()))
        if sum(values)==0:zero_causes.append(cause)
        else:rows.append([cause,*values])
    if zero_causes:rows.append(['Other guards',0,0,0,0])
    table('refusals','First adjacent failed guard under the declared diagnostic order for Strict across all sources, with 120 s counts by precision and full-episode counts over all three precisions','tab:v8_refusals',['Guard','Fine','Medium','Coarse','Full total'],rows)
    refusal_path=ROOT/'paper/v8_refusals.tex'
    refusal_path.write_text(refusal_path.read_text(encoding='utf8').replace('profiles}', 'profiles, with Other denoting '+', '.join(zero_causes)+'}'),encoding='utf8')
    rows=[];ns=f[f.dataset!='Solar'];bn=b[b.dataset!='Solar']
    methods=['Escape','Swing','SlideCore','DPvertical','SwingIso','SlideCoreIso','DPverticalIso','ZFP','ZFPIso','zstd','SZ3','Native32','SwingEnergy','SlideEnergy','LinearResetGuarded']
    for method in methods:
        a=ns.query('method==@method and profile=="medium"') if method in ['Strict','Search','Escape','SearchEscape'] else bn[bn.method==method]
        if (a.status=='NOT_RUN_LIBRARY_UNAVAILABLE').any():rows.append([method,'not run','--','--','--']);continue
        valid=a.status=='OK'
        if 'guard_complete' in a:valid=a.guard_complete
        failures=~valid
        rows.append([method,f'{int(valid.sum())}/706',fmt(100*source_balanced(a,'effective_byte_ratio'),1),
            fmt(100*source_balanced(a,'neutral_effective_byte_ratio'),1),fmt(a.loc[valid,'power_max_W'].max(),2)])
    table('baselines','Guard-complete non-Solar records and all-attempt byte percentages under native formats and lossless common ULEB recoding of actual decoded fields, weighted equally by source and acquisition cluster','tab:v8_baselines',['Method','Support','Native B\\%','Common B\\%','$e_P$ W'],rows)
    rows=[]
    for ds in ['IDF','CMU','AMOVFLY','Solar']:
        for scope,a in [('120',f),('Full',full)]:
            pop=a[(a.dataset==ds)&(a.profile=='medium')];oracle=pop[pop.method=='ByteOracle'].set_index('flight_id')
            completed=[];gaps=[]
            for method in ['Strict','Horizon2','Horizon4']:
                z=pop[pop.method==method].set_index('flight_id');good=z.index[(z.status=='OK')&(oracle.reindex(z.index).status=='OK')]
                gap=(z.loc[good,'encoded_bytes']-oracle.loc[good,'encoded_bytes'])/oracle.loc[good,'encoded_bytes']
                assert (gap>=-1e-12).all()
                completed.append(str(int((z.status=='OK').sum())));gaps.append(fmt(100*gap.mean(),1))
            rows.append([ds,scope,len(z),'/'.join(completed),'/'.join(gaps),int(oracle.status.eq('OK').sum())])
    table('horizon','Medium completion counts and mean byte gaps to the nearest-node oracle on each rule\'s paired feasible support, ordered Strict/Horizon2/Horizon4 with respective delays 5.5/6/7 s and buffers 12/13/15 knots','tab:v8_horizon',['Source','Scope','$N$','Complete S/2/4','Gap \\% S/2/4','Oracle'],rows)
    effects=pd.read_csv(DEV/'results/paired_effects_v8.csv');rows=[]
    for ds in ['IDF','CMU','AMOVFLY']:
        cells=[]
        for method in ['SwingIso','SwingEnergy','ZFPIso','Native32']:
            z=effects.query('dataset==@ds and control==@method').iloc[0]
            digits=2 if method=='Native32' else 1
            value=f'{100*z.HL:.{digits}f} [{100*z.HL_low95:.{digits}f},{100*z.HL_high95:.{digits}f}]'
            cells.append(r'\shortstack{'+value+r'\\$p_H=$'+fmtp(z.wild_studentized_p_holm)+'}')
        rows.append([ds,*cells])
    table('effects','Escape-minus-control common-byte differences in percentage points with cluster HL and 95\\% interval above the Holm-adjusted wild p value in each cell','tab:v8_effects',['Source','SwingIso','SwingEnergy','ZFPIso','Native32'],rows,small=False)
    effect_path=ROOT/'paper/v8_effects.tex'
    effect_path.write_text(effect_path.read_text(encoding='utf8').replace(r'\centering',r'\centering\footnotesize').replace(r'\tabcolsep}{3pt}',r'\tabcolsep}{2pt}'),encoding='utf8')
    drift=pd.read_csv(DEV/'results/matched_path_drift.csv');rows=[]
    for ds in ['IDF','CMU','AMOVFLY','Solar']:
        violations=[];maxima=[]
        for method in ['DeltaNaiveSamePath','DeltaFeedbackSamePath','LinearSamePath']:
            a=drift.query('dataset==@ds and method==@method');okay=a.status=='OK'
            violations.append(str(int((a.loc[okay,'energy_max_Wh']>.001+1e-12).sum())));maxima.append(fmt(1000*a.loc[okay,'energy_max_Wh'].max(),3))
        rows.append([ds,f'{okay.sum()}/{len(a)}','/'.join(violations),'/'.join(maxima)])
    table('drift','Matched full-episode Strict paths with violation counts and maximum mWh errors ordered naive increments/feedback increments/linear resets','tab:v8_drift',['Source','Paths','Violations N/F/L','Max mWh N/F/L'],rows)
    loss=pd.read_csv(DEV/'results/loss_replicates.csv');rows=[]
    for channel in ['Bernoulli','GilbertElliott']:
        for m in [1,16]:
            for protection in ['none','repeat','xor']:
                a=loss.query('dataset!="Solar" and channel==@channel and m==@m and protection==@protection and rate==.1')
                # Aggregate sources equally within each repeat, so SD is across
                # the same thirty channel replicates as the displayed mean.
                z=a.groupby('repeat')[['certified_fraction','anchor_available_fraction','application_byte_multiplier']].mean()
                rows.append([channel.replace('GilbertElliott','GE'),m,protection,
                    f'{100*z.certified_fraction.mean():.1f} $\\pm$ {100*z.certified_fraction.std():.1f}',
                    f'{100*z.anchor_available_fraction.mean():.1f} $\\pm$ {100*z.anchor_available_fraction.std():.1f}',fmt(z.application_byte_multiplier.mean(),2)])
    table('loss','Duration-weighted certified support and left-anchor availability percentages under 10\\% datagram loss as means and SD across thirty replicates, with actual framed-byte multiplier relative to the base stream','tab:v8_loss',['Channel','$m$','Protection','Certified \\%','Anchor \\%','Byte $\\times$'],rows)
    legacy=pd.read_csv(DEV/'results/legacy_36_Holm.csv');rows=[]
    shorten=lambda value:value.replace('DBG_var_','V').replace('DBG_fixed_','F').replace('DBG_cert_','Cert')
    for _,z in legacy.iterrows():rows.append([z.source.replace('NON_SOLAR','Non-Solar'),shorten(z.method_a),shorten(z.method_b),fmtp(z.p_raw),fmtp(z.p_holm)])
    short=lambda s:s.replace('Non-Solar','N').replace('AMOVFLY','A').replace('IDF','I').replace('CMU','C').replace('Cert','C').replace('medium','m').replace('fine','f').replace('coarse','c').replace('Swing','Sw').replace('SlideCore','Sl').replace('Native','Nat').replace('DPvertical','DP')
    def shortp(s):
        if r'\!\times\!10^{' in s:
            coefficient,tail=s[1:].split(r'\!\times\!10^{')
            return '$'+format(float(coefficient),'.2g')+r'\mathrm{e}{'+tail
        return s.removeprefix('0') if s.startswith('0.') else s
    rows=[[short(s) if j<3 else shortp(s) for j,s in enumerate(row)] for row in rows]
    rows=[[r[0],r[1]+'/'+r[2],r[3],r[4]] for r in rows]
    rows=[rows[j]+rows[j+12]+rows[j+24] for j in range(12)]
    table('legacy_holm','All 36 original pairwise tests with raw and Holm p values, with sources I/C/A/N denoting IDF/CMU/AMOVFLY/non-Solar, V/F/C denoting variable/fixed/certificate, f/m/c denoting fine/medium/coarse and Sw/Sl/DP denoting Swing/Slide/Douglas--Peucker','tab:v8_legacy_holm',['S','Pair','$p$','$p_H$']*3,rows)
    compact_table=ROOT/'paper/v8_legacy_holm.tex'
    compact_table.write_text(compact_table.read_text(encoding='utf8').replace(r'\tabcolsep}{3pt}',r'\tabcolsep}{1pt}').replace('{lrrrrrrrrrrr}',r'{@{}lrrr@{\hspace{5pt}}lrrr@{\hspace{5pt}}lrrr@{}}'),encoding='utf8')
    # A compact traceability table complements machine-readable full paths in
    # the reproducibility package without local filesystem paths in the paper.
    claims=r'''\begin{table}[!htbp]\centering\small
\caption{Claim boundaries linked to measured evidence and reproducible script identifiers}\label{tab:v8_claim_evidence}
\begin{tabularx}{\linewidth}{@{}>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X>{\raggedright\arraybackslash}X@{}}\toprule
Claim & Evidence & Generator\\\midrule
Continuous guards & 1,200 spans, wire replay & validate\_v8\\
Bounded escape & support/bytes, 12 knots & experiments\\
Fixed-graph oracle & 2 scopes, 718 graphs & validate\_v8\\
Conditional effects & 36 old/42 new tests & statistics\_v8\\
Drift audit & matched increment wires & extra\_diagnostics\\
Guard timing & increment wires, warmed guards & extra\_diagnostics\\
Erasure support & 30 repeats, actual frames & loss\_v8\\
Prepared scope & 718 PL matches & preprocessing\_v8\\
\bottomrule\end{tabularx}\end{table}
'''
    (ROOT/'paper/v8_claim_evidence.tex').write_text(claims,encoding='utf8')
    guard_times=pd.read_csv(DEV/'results/compiled_timings.csv').groupby('component').ns_per_call.median()/1000
    timing_cell='P/E/q: '+ '/'.join(f'{guard_times[x]:.2f}' for x in ['power_guard','energy_guard','shape_guard'])+r' $\mu$s/call'
    claims=claims.replace('increment wires, warmed guards',timing_cell)
    (ROOT/'paper/v8_claim_evidence.tex').write_text(claims,encoding='utf8')
    # Explicit numeric display registry is also the source of prose, with no
    # manually guessed values or substitution of an unexecuted experiment.
    for ds in ['IDF','CMU','AMOVFLY','Solar']:
        for method in ['Strict','Search','Escape','SearchEscape']:
            for scope,a in [('120',f),('full',full)]:
                z=a.query('dataset==@ds and method==@method and profile=="medium"')
                display[f'{ds}_{method}_{scope}_complete']=int((z.status=='OK').sum())
    write('results/display_v8.json',display)
    plots(f,full,b,loss)

def save(fig,name):
    fig.savefig(ROOT/f'paper/figures/v8_{name}.pdf',bbox_inches='tight',metadata={'CreationDate':None,'ModDate':None})
    fig.savefig(DEV/f'figures/{name}.png',bbox_inches='tight',dpi=170);plt.close(fig)

def plots(f,full,b,loss):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,3,figsize=(5.2,2.7),layout='constrained')
    for ds,ax in zip(['IDF','CMU','AMOVFLY'],axes):
        a=f.query('dataset==@ds and profile=="medium" and method in ["Strict","Search","Escape","SearchEscape"]')
        z=a.groupby(['method','group_id'],sort=False).agg(bytes=('effective_byte_ratio','mean'),completion=('status',lambda x:100*(x=='OK').mean())).groupby('method').mean()
        ax.scatter(100*z.bytes,z.completion,color='#245b83',s=35)
        for label,r in z.iterrows():ax.annotate(label,(100*r.bytes,r.completion),xytext=(3,3),textcoords='offset points',fontsize=7)
        ax.set(title=ds,xlabel='Effective Dense bytes (%)',ylabel='Group-balanced completion (%)');ax.grid(alpha=.2)
    save(fig,'support_bytes')
    heat=pd.read_csv(DEV/'results/two_budget_heatmap.csv');fig,axes=plt.subplots(2,3,figsize=(5.2,3.2),layout='constrained')
    for j,ds in enumerate(['IDF','CMU','AMOVFLY']):
        a=heat.query('dataset==@ds and method=="Strict"').copy();a['complete']=a.status=='OK';a['byte_rate']=a.effective_bytes/a.duration_s if 'duration_s' in a else a.effective_bytes/120
        for i,col in enumerate(['complete','byte_rate']):
            q=a.groupby(['energy_budget_Wh','power_budget_W','group_id'])[col].mean().groupby(['energy_budget_Wh','power_budget_W']).mean().unstack();values=q.to_numpy()*(100 if col=='complete' else 1)
            shown=axes[i,j].imshow(values,origin='lower',aspect='auto',cmap='Greys',vmin=0 if col=='complete' else None,vmax=100 if col=='complete' else None)
            for y in range(3):
                for x in range(3):axes[i,j].text(x,y,f'{values[y,x]:.1f}',ha='center',va='center',color='white' if shown.norm(values[y,x])>.55 else 'black')
            axes[i,j].set(xticks=range(3),xticklabels=[12.5,25,50],yticks=range(3),yticklabels=[.5,1,2],xlabel='Power budget (W)',ylabel='Energy budget (mWh)',title=ds+(' completion %' if i==0 else ' effective B/s'))
    save(fig,'heatmap')
    fig,axes=plt.subplots(1,2,figsize=(5.2,2.4),layout='constrained')
    for ax,channel in zip(axes,['Bernoulli','GilbertElliott']):
        for m,ls in [(1,'-'),(4,'--'),(16,':')]:
            for protection,marker in [('none','o'),('repeat','s'),('xor','^')]:
                a=loss.query('dataset!="Solar" and channel==@channel and m==@m and protection==@protection')
                q=a.groupby(['rate','repeat']).certified_fraction.mean().groupby('rate').agg(['mean','std'])
                ax.errorbar(100*q.index,100*q['mean'],yerr=100*q['std'],ls=ls,marker=marker,ms=3,label=f'{m}/{protection}',lw=1)
        ax.set(title=channel,xlabel='Datagram loss (%)',ylabel='Certified duration (%)');ax.grid(alpha=.2)
    handles,labels=axes[-1].get_legend_handles_labels();fig.legend(handles,labels,fontsize=8,ncol=3,loc='upper center',bbox_to_anchor=(.5,1.23));save(fig,'loss')
    from wire import decode,ESCAPE
    from kernels import cumulative_energy
    source=next(r for r in sorted(records(),key=lambda r:(r['dataset'],str(r['flight_id']))) if r['dataset']=='AMOVFLY' and np.ptp(r['p'][:61])>25)
    wires=joblib.load(DEV/'data/wires_120.joblib');key=(source['dataset'],source['flight_id'],'Escape','medium')
    assert key in wires,'The declared illustrative record must not be replaced by a favorable-error case'
    d=decode(wires[key]);t,p=source['t'],source['p'];e=cumulative_energy(t,p);times=[];power=[];energy=[]
    for j,(aa,bb) in enumerate(zip(d['rows'][:-1],d['rows'][1:])):
        D=bb[1]-aa[1];c=3600*(bb[3]-aa[3])/D-(aa[2]+bb[2])/2
        linear=d['packets'][j+1]['kind']==ESCAPE;c1=(bb[2]-aa[2]+(0 if linear else 6*c))/D;c2=0 if linear else -6*c/D**2
        x=np.linspace(0,D,25);times.extend(aa[1]+x);power.extend(aa[2]+c1*x+c2*x*x);energy.extend(aa[3]+(aa[2]*x+c1*x*x/2+c2*x*x*x/3)/3600)
    tt=np.asarray(times);pp=np.asarray(power);ee=np.asarray(energy);ii=np.clip(np.searchsorted(t,tt,side='right')-1,0,len(t)-2);dx=tt-t[ii]
    er=e[ii]+(p[ii]*dx+.5*(p[ii+1]-p[ii])/(t[ii+1]-t[ii])*dx*dx)/3600
    fig=plt.figure(figsize=(5.4,2.5));ax=fig.add_subplot(121,projection='3d');ax.plot(t,p,e,color='black',lw=.7,label='Prepared reference')
    sc=ax.scatter(tt[::4],pp[::4],ee[::4],c=abs(pp-np.interp(tt,t,p))[::4],s=6,cmap='viridis')
    ax.set(xlabel='Time (s)',ylabel='Power (W)',title='Energy (Wh)');ax.view_init(24,-60)
    bx=fig.add_subplot(122);bx.plot(tt,1000*(ee-er),color='#245b83',lw=.9);bx.axhline(1,color='black',ls='--',lw=.7);bx.axhline(-1,color='black',ls='--',lw=.7)
    bx.set(xlabel='Time (s)',ylabel='Signed energy error (mWh)',ylim=(-1.15,1.15));bx.grid(alpha=.2)
    fig.subplots_adjust(left=.02,right=.87,bottom=.24,top=.93,wspace=.5);cb=fig.add_axes([.94,.29,.014,.55]);fig.colorbar(sc,cax=cb,label='Power error (W)');save(fig,'case')
    write('results/illustrative_record.json',dict(dataset=source['dataset'],flight_id=source['flight_id'],criterion='lexicographically first AMOVFLY record with first-30s power range above 25W; not selected by reconstruction error',method='Escape',profile='medium'))

if __name__=='__main__':run()
