"""Illustrated vector roles for normal candidates, guarded escapes and receiver checks."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
from common import *

def run():
    step0();fig,ax=plt.subplots(figsize=(5.1,3.2));ax.set(xlim=(0,10.1),ylim=(0,7.6));ax.axis('off')
    def box(x,y,w,h,title,text,color):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.06,rounding_size=.10',facecolor=color,edgecolor='#56636f',lw=.7))
        ax.text(x+.12,y+h-.17,title,fontsize=7.3,weight='bold',va='top',color='#203746')
        ax.text(x+.12,y+h-.57,text,fontsize=6.7,va='top',linespacing=1.35,color='#203746')
    def arrow(a,b,label=None,color='#465b6b'):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=8,lw=.8,color=color))
        if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.05,label,fontsize=6,ha='center',bbox=dict(facecolor='white',edgecolor='none',pad=.4))
    box(.15,5.5,4.3,1.7,'1  Prepared telemetry reference','Finite nonnegative power on a .5 s grid\nAbsolute prefix energy by integration\nNative gaps and sensor limits retained','#e5eff7')
    box(5.25,5.5,4.3,1.7,'2  Construct actual candidates','Nearest counts or bounded neighbors\nGuarded linear escape at adjacent failure\nExplicit type, sequence and absolute fields','#f9edd8')
    box(.15,2.95,4.3,1.7,'3  Decode the packed values','Reconstruct exactly the emitted fields\nConservative quadratic or flagged line\nCandidate bytes are measured directly','#e5eff7')
    box(5.25,2.95,4.3,1.7,'4  Sender continuous guards','Power and absolute-energy discrepancy\nNonnegative power and duration cap\nFinite extrema over the reference pieces','#f9edd8')
    box(.15,.4,4.3,1.7,'5  Commit or report refusal','Emit only a checked segment\nKeep the previous actual anchor\nCharge escape, prefix and fallback bytes','#e4f1e8')
    box(5.25,.4,4.3,1.7,'6  Receiver and erasure audit','Check syntax, order, shape and CRC\nFooter detects a missing end if delivered\nDiscarded-sample errors remain assertions','#e4f1e8')
    arrow((4.51,6.35),(5.19,6.35));arrow((5.8,5.43),(3.65,4.72),'packed bytes')
    arrow((4.51,3.8),(5.19,3.8));arrow((5.8,2.88),(3.65,2.17),'accepted only')
    arrow((4.51,1.25),(5.19,1.25));arrow((9.63,3.8),(9.63,5.8),None,'#9a6332')
    ax.text(9.85,4.8,'retry / refuse',fontsize=6.1,rotation=90,ha='center',va='center',color='#9a6332')
    fig.subplots_adjust(left=.01,right=.99,top=.99,bottom=.01)
    fig.savefig(ROOT/'paper/figures/iccies_workflow.pdf',bbox_inches='tight',metadata={'CreationDate':None,'ModDate':None})
    fig.savefig(DEV/'figures/workflow.png',bbox_inches='tight',dpi=180);plt.close(fig)

if __name__=='__main__':run()
