"""List every zipmod in BetterRepack's public AI/HS2 Sideloader modpacks and keep the venom / symbiote ones
(2026-11-15: 20,982 zipmods, 1 hit - Fouetty's Venom Marvel Rivals, a Studio item).  Writes data\\br_venom_hits.json."""
import concurrent.futures as cf, html, json, os, re, sys, urllib.parse, urllib.request
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "br_venom_hits.json")
BASE = "https://sideload.betterrepack.com/download/AISHS2/"
PACKS = ["Sideloader Modpack", "Sideloader Modpack - Exclusive HS2", "Sideloader Modpack - Studio",
         "Sideloader Modpack - Bleeding Edge", "Sideloader Modpack - Exclusive AIS", "Sideloader Modpack - Maps (HS2 Game)"]
RX = re.compile(r"venom|symbio|carnage|gwenom|klyntar|ヴェノム", re.I)
def get(url):
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            pass
    return ""
def links(s):
    return [html.unescape(urllib.parse.unquote(x)) for x in re.findall(r'href="([^"?/][^"]*)"', s) if not x.startswith("http")]
jobs = []
for p in PACKS:
    top = get(BASE + urllib.parse.quote(p) + "/")
    for d in sorted(set(x for x in links(top) if x.endswith("/"))):
        jobs.append((p, d))
print("folders", len(jobs), flush=True)
hits, total = [], 0
def one(job):
    p, d = job
    s = get(BASE + urllib.parse.quote(p) + "/" + urllib.parse.quote(d))
    files = [x for x in links(s) if x.lower().endswith((".zipmod", ".zip"))]
    return p, d, files
with cf.ThreadPoolExecutor(4) as ex:
    for p, d, files in ex.map(one, jobs):
        total += len(files)
        for f in files:
            if RX.search(f) or RX.search(d):
                hits.append({"pack": p, "folder": d, "file": f,
                             "url": BASE + urllib.parse.quote(p) + "/" + urllib.parse.quote(d) + urllib.parse.quote(f)})
json.dump(hits, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("files", total, "hits", len(hits))
for h in hits:
    print(h["pack"], "|", h["folder"], "|", h["file"])
