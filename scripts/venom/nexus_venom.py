"""Nexus Mods public v2 GraphQL (no key): every published mod whose NAME has venom / symbiote / gwenom / carnage /
symbiote-ish words, all games; keeps id, game, author, summary, adult flag, downloads, picture.
Writes the full list to data\\nexus_venom.json (2026-11-15: 1,891 mods; make_venom_page.py filters the female ones -
the repo copy keeps only those 64).  No key needed; see the Nexus API notes in the repo memory / docs."""
import json
import os
import time
import urllib.request

URL = "https://api.nexusmods.com/v2/graphql"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "nexus_venom.json")
TERMS = ["venom", "symbiote", "symbiot", "gwenom", "carnage", "shevenom", "she-venom", "venomized", "klyntar",
         "anti-venom", "agent venom", "riot"]
Q = """query($f: ModsFilter, $o: Int) { mods(filter: $f, count: 20, offset: $o) { totalCount nodes {
  modId name summary author adultContent downloads endorsements pictureUrl createdAt updatedAt
  uploader { name } game { id name domainName } } } }"""


def post(query, variables):
    data = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json",
                                                          "User-Agent": "Mozilla/5.0"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3)
    raise err


mods = {}
for term in TERMS:
    off = 0
    while True:
        res = post(Q, {"f": {"name": [{"value": term, "op": "WILDCARD"}]}, "o": off})
        if "errors" in res:
            print("ERR", term, res["errors"][:1])
            break
        block = res["data"]["mods"]
        for n in block["nodes"]:
            mods[(n["game"]["id"], n["modId"])] = n
        off += 20
        print(term, off, "/", block["totalCount"], flush=True)
        if off >= block["totalCount"] or off >= 600:
            break
json.dump(list(mods.values()), open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("NEXUS_VENOM=" + json.dumps({"mods": len(mods)}))
