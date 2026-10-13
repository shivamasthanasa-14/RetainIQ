import math
import re
from collections import Counter
from pathlib import Path

STOP = set('the a an and or to for of in on is it my our we you can how with from at this that have has be i please'.split())
def tokens(text):
    # Light plural normalization is search preprocessing, not AI classification.
    return [w[:-1] if w.endswith('s') and len(w) > 4 and not w.endswith('ss') else w
            for w in re.findall(r'[a-z0-9]+', text.lower()) if w not in STOP and len(w) > 2]

class Knowledge:
    def __init__(self, directory):
        self.docs = [{'id': p.stem, 'title': p.read_text(encoding='utf-8').splitlines()[0].lstrip('# '),
                      'text': p.read_text(encoding='utf-8')} for p in sorted(Path(directory).glob('*.md'))]
        self.counts = [Counter(tokens(d['text'] + ' ' + d['title'] + ' ' + d['title'])) for d in self.docs]
        self.idf = {w: math.log((len(self.docs) + 1) / (1 + sum(w in c for c in self.counts))) + 1
                    for c in self.counts for w in c}

    def retrieve(self, text, limit=3):
        query = Counter(tokens(text))
        def vector(counter):
            return {w: count * self.idf.get(w, 1) for w, count in counter.items()}
        q = vector(query)
        qnorm = math.sqrt(sum(v*v for v in q.values())) or 1
        hits = []
        for doc, count in zip(self.docs, self.counts):
            v = vector(count)
            score = sum(x * v.get(w, 0) for w, x in q.items()) / (qnorm * (math.sqrt(sum(x*x for x in v.values())) or 1))
            if score >= .10:
                hits.append({**doc, 'score': round(score, 3)})
        return sorted(hits, key=lambda d: d['score'], reverse=True)[:limit]
