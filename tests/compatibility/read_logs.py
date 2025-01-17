import json
import sys
import codecs
import numpy as np
from docopt import docopt

#if __name__ == '__main__':
#    args = docopt(__doc__, version='Ideal Words 0.1')
#    bert_json = args['<filename>']

param_sets = []
with codecs.open(sys.argv[1],'rU','utf-8') as f:
    for line in f:
       param_sets.append(json.loads(line))

best_vals = []
for param_set in param_sets:
    best_vals.append(param_set["target"])

best_indices = np.argsort(best_vals)[-20:][::-1]

rows = []
columns=["target"]
for k,v in param_sets[0]["params"].items():
    columns.append(k[:6])

for best in best_indices:
    param_set = param_sets[best]
    row = [str(param_set["target"])[:6]]
    for k,v in param_set["params"].items():
        if k not in ["lrate","wdecay"]:
            row.append(str(int(v)))
        else:
            row.append(str(v)[:5])
    rows.append(row)

print('\t'.join([i for i in columns]))
for row in rows:
    print('\t'.join([i for i in row]))
