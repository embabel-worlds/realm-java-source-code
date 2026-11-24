"""realm-java-source-code live battery. Run by tests/verify.sh, which states the environment.

L1  every view of this realm answers BY NAME, with the arguments a caller would pass.
L2  exact reconciliation against the sources jar the realm ships, read here with zipfile: a
    file's path and line count, a method's overloads and the lines they span, every span a
    view returns holding the name it claims, and the shipped source matching the jar (no drift).
L3  cost: not applicable. Every producer reads local files through the `source-tree` kind; no
    view makes a call to a remote source, so there is no source-call ceiling to hold.
"""
import base64, glob, json, os, re, sys, urllib.error, urllib.request, zipfile

BASE = os.environ.get("APPLIANCE", "http://127.0.0.1:8080").rstrip("/")
HDR = {"Authorization": "Basic " + base64.b64encode(os.environ["AUTH"].encode()).decode(),
       "Content-Type": "application/json"}
JAR = "data/jars/spring-core-6.2.18.jar"          # realm-java-code's example jar
SOURCES = "data/sources/spring-core-6.2.18-sources.jar"
fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + ("" if ok or not detail else f": {detail}"))
    if not ok:
        fails.append(name)


def view(name, args):
    req = urllib.request.Request(f"{BASE}/api/v1/views/{name}/invoke", headers=HDR,
                                 data=json.dumps({"args": args}).encode())
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.loads(r.read(), strict=False)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} {e.read().decode()[:300]}"
    except (urllib.error.URLError, OSError) as e:
        return None, f"unreachable: {e}"
    err = d.get("error")
    return (None, str(err)[:300]) if err else (d.get("data") or [], None)


# ---- ground truth, from the sources jar -----------------------------------------------------
z = zipfile.ZipFile(SOURCES)
def source(path):
    return z.read(path).decode("utf-8").split("\n")

SU = "org.springframework.util.StringUtils"
SU_PATH = "org/springframework/util/StringUtils.java"
su = source(SU_PATH)
SU_LINES = len(z.read(SU_PATH).decode("utf-8").splitlines())
HASTEXT = [i for i, l in enumerate(su, 1) if re.search(r"\bstatic boolean hasText\(", l)]
print(f"== L0: {SOURCES}: {SU_PATH} has {SU_LINES} lines; hasText declared at {HASTEXT}")

# ---- L1: every view by name -----------------------------------------------------------------
FIELD = "org.springframework.util.ClassUtils.commonClassCache"
ARGS = {
    "JavaTypeSource": {"jar": JAR, "type": SU},
    "JavaMethodDeclarations": {"jar": JAR, "type": SU, "method": "hasText"},
    "JavaCallersWithCode": {"jar": JAR, "type": "java.util.Map", "method": "put"},
    "JavaMapPutCallSites": {"jar": JAR}, "JavaFieldMutationCode": {"jar": JAR, "field": FIELD},
    "JavaSourceDrift": {"jar": JAR, "package": "org.springframework.util"},
    "JavaLongestMethods": {"jar": JAR}, "JavaExplicitLocalsVarWouldKeep": {"jar": JAR},
    "JavaMethodLocals": {"jar": JAR, "type": SU, "method": "tokenizeToStringArray"},
    "SpringCoreClassCacheCode": {}, "SpringCoreHasText": {}, "SpringCoreLongestMethods": {},
    "SpringCoreStringLocalsVarWouldKeep": {},
}
names = sorted({m.group(1) for f in glob.glob("views/*.yml")
                for m in re.finditer(r"^- name:\s*(\S+)", open(f).read(), re.M)})
print(f"== L1: {len(names)} views by name")
results = {}
for name in names:
    if name not in ARGS:
        check(f"view {name}", False, "no arguments in tests/verify.py: add them")
        continue
    rows, err = view(name, ARGS[name])
    results[name] = rows
    check(f"view {name}: {len(rows) if rows is not None else 0} row(s)", err is None and bool(rows), err or "no rows")

# ---- L2: reconcile against the sources ------------------------------------------------------
print("== L2: the views against the shipped sources")
r = (results.get("JavaTypeSource") or [{}])[0]
check("JavaTypeSource path", str(r.get("path", "")).endswith(SU_PATH), f"{r.get('path')}")
check("JavaTypeSource lines", r.get("lines") == SU_LINES, f"{r.get('lines')} vs {SU_LINES}")
check("JavaTypeSource one candidate", r.get("candidates") == 1, f"{r.get('candidates')}")

for view_name in ("JavaMethodDeclarations", "SpringCoreHasText"):
    rows = results.get(view_name) or []
    spans = sorted((row.get("fromLine") or 0, row.get("toLine") or 0) for row in rows) if view_name != "SpringCoreHasText" else None
    if spans is not None:
        covered = [any(a <= line <= b for a, b in spans) for line in HASTEXT]
        check(f"{view_name} hasText: {len(HASTEXT)} overloads, each declaration line inside one span",
              len(rows) == len(HASTEXT) and all(covered), f"{spans} vs {HASTEXT}")
        check(f"{view_name}: every overload matches the jar", all(row.get("matches") for row in rows))
    check(f"{view_name}: every body shows hasText(", len(rows) == len(HASTEXT)
          and all("hasText(" in str(row.get("code") or "") for row in rows))

drift = results.get("JavaSourceDrift") or []
check(f"JavaSourceDrift org.springframework.util: {len(drift)} classes, none drifted",
      bool(drift) and all(row.get("drifted") == 0 for row in drift),
      str([row for row in drift if row.get("drifted")][:3]))

for view_name in ("JavaLongestMethods", "SpringCoreLongestMethods"):
    rows = results.get(view_name) or []
    bad = []
    for row in rows:
        lines = source(row["path"].split("!")[-1]) if row.get("path") in z.namelist() else None
        if lines is None:
            path = next((n for n in z.namelist() if n.endswith(row.get("path", "?"))), None)
            lines = source(path) if path else []
        name = row["method"] if row["method"] != "<init>" else row["owner"].rsplit(".", 1)[-1].split("$")[-1]
        frm = row.get("fromLine")
        to = frm + row["lines"] - 1 if frm else 0
        if not lines or name not in "\n".join(lines[frm - 1:to]) or (row.get("toLine") not in (None, to)):
            bad.append((row.get("owner"), row.get("method"), frm, row.get("lines")))
    check(f"{view_name}: {len(rows)} spans each hold the method they name", bool(rows) and not bad, str(bad[:3]))
    longest = [row["lines"] for row in rows]
    check(f"{view_name}: ranked longest first", longest == sorted(longest, reverse=True), str(longest))

locals_ = {row.get("name") for row in results.get("JavaMethodLocals") or []}
# tokenizeToStringArray's four-argument overload declares exactly these; the two-argument one none.
check("JavaMethodLocals tokenizeToStringArray: st, tokens, token", locals_ == {"st", "tokens", "token"}, str(locals_))

print("== L3: not applicable — every producer reads local files; no source calls to bound")
if fails:
    print(f"FAILED: {len(fails)} check(s): {', '.join(fails)}")
    sys.exit(1)
print("ALL CHECKS PASS")
