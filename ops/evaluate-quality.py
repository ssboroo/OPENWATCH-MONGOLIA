#!/usr/bin/env python3
"""Evaluate independently human-reviewed pairs. No synthetic accuracy claims.
Input JSONL: pair_id, expected (boolean), predicted (boolean), reviewer,
reviewed_at, left_url, right_url. Split evaluation data from tuning data.
"""
import argparse,json
from pathlib import Path

def evaluate(rows):
    seen=set();tp=fp=tn=fn=0
    for r in rows:
        if not all(r.get(k) for k in ('pair_id','reviewer','reviewed_at','left_url','right_url')):raise ValueError('Human review provenance required')
        if r['pair_id'] in seen:raise ValueError('Duplicate pair')
        seen.add(r['pair_id'])
        if type(r.get('expected')) is not bool or type(r.get('predicted')) is not bool:raise ValueError('Labels must be boolean')
        if r['predicted'] and r['expected']:tp+=1
        elif r['predicted']:fp+=1
        elif r['expected']:fn+=1
        else:tn+=1
    return {'reviewed_pairs':len(seen),'true_positive':tp,'false_positive':fp,'true_negative':tn,'false_negative':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,'false_positive_rate':fp/(fp+tn) if fp+tn else None,'limitation':'Only this reviewed sample; not population-wide accuracy. Reviewers must label independently of predictions.'}
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input');parser.add_argument('--output',required=True);args=parser.parse_args()
    result=evaluate([json.loads(line) for line in Path(args.input).read_text().splitlines() if line.strip()]);Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
