"""CLI experimental de treinamento; usa somente os arquivos locais existentes."""

import argparse
import json
from pathlib import Path

from app.supervised.training.experiment import run


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/synthetic/level2-seed42'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=42)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]/'artifacts'/'supervised'
    output=args.output.resolve()
    if output==root or not output.is_relative_to(root):
        parser.error('Saída deve estar em subdiretório novo de artifacts/supervised/ (ignorado pelo Git)')
    report=run(args.data,output,args.seed)
    print(json.dumps({'output':str(output),'temporal_split':report['scenarios']['temporal']['split'],
                      'validation_best_ap':report['scenarios']['temporal']['validation_best_ap'],
                      'test':{name:entry['partitions']['test'] for name,entry in report['scenarios']['temporal']['models'].items()}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
