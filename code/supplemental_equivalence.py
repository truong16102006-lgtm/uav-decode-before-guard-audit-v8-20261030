"""Explicitly exploratory ordinary-Swing TOST, added after result inspection."""
from common import *
from statistics_v8 import holm


def run():
    step0()
    source=DEV/'results/paired_effects_v8.csv';before=sha(source)
    frame=pd.read_csv(source);rows=frame[frame.control.eq('Swing')].to_dict('records')
    assert len(rows)==3
    holm(rows,'tost_p_max','tost_p_holm')
    for row in rows:
        row['TOST_equivalent_after_Holm']=row['tost_p_holm']<.05
        row['analysis_status']='exploratory supplemental ordinary-Swing comparison added after result inspection'
    pd.DataFrame(rows).to_csv(DEV/'results/tost_ordinary_swing_exploratory.csv',index=False)
    assert sha(source)==before
    write('audit/supplemental_equivalence.json',dict(passed=True,comparisons=3,margin=.01,alpha=.05,Holm_family=3,
          primary_42_comparisons_unchanged=True,source_sha256=before,
          timing='Post-result supplement to cover ordinary Swing explicitly; declared energy-aware Swing TOST remains the primary family.'))


if __name__=='__main__':run()
