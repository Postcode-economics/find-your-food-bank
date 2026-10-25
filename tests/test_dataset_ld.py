"""GSC 'Datasets' structured data (25 Oct 2026): required + recommended fields present, no nested Dataset without description."""
import os, re, json, unittest
R = os.path.join(os.path.dirname(__file__), '..')
class T(unittest.TestCase):
    def test_dataset(self):
        h = open(os.path.join(R, 'index.html'), encoding='utf-8').read()
        d = json.loads(re.search(r'data-ld="dataset">(.*?)</script>', h, re.S).group(1))
        for k in ('name', 'description', 'url', 'license', 'creator', 'distribution', 'dateModified'): self.assertTrue(d.get(k), k)
        self.assertTrue(50 <= len(d['description']) <= 5000)
        for x in d['distribution']: self.assertTrue(os.path.exists(os.path.join(R, x['contentUrl'].split('helpmap.uk/')[1])), x)
        for x in d['isBasedOn']: self.assertNotEqual(x['@type'], 'Dataset')
if __name__ == '__main__': unittest.main()
