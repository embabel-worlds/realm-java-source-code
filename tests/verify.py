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


# A figure the engine marks short is not the realm's figure, and a battery that counts it reports
# drift that is the source's. short(d) reads an answer's own error, reason, warnings and outcome and
# is None when the answer is whole, else the line that stands in for the figure: "REFUSED: <why>"
# or "PARTIAL <n>: <the engine's reason>". It reads both wires: a query answer (`rows`, `warnings`
# as strings opening with the engine's code) and a view envelope (`status`, `outcome`, `warnings`
# as {code, message}).
# Raw warning codes that mean rows or values may be missing (the engine's incompleteness kinds).
# Cost notes (FILTERED_IN_GRAPH, AGGREGATE_NOT_PUSHED, EMPTY_NOT_KEPT, PUSHDOWN_VALUE_UNMATCHED),
# FILTER_STARVED (an honest empty), STALE_COPY, FIELDS_WITHHELD and UNKNOWN_VIA leave every row in place.
SHORT_CODES = (
    "PARTIAL_RESULT", "PRODUCER_ERROR", "NEEDS_FILTER", "NEEDS_PRODUCER", "FILTER_REJECTED",
    "UNPUSHED_FILTER", "AMBIGUOUS_LABEL", "INCOMPLETE_TRAVERSAL", "INCOMPLETE_RANKING",
    "INCOMPLETE_AGGREGATE", "INCOMPLETE_INPUT", "MATERIALIZATION_FAILED", "REDUCTION_FAILED",
    "UNPARSEABLE_ANSWER", "TERMS_UNAVAILABLE", "COMPUTE_FAILED", "PROPERTY_NOT_STORED",
    "FOLLOW_CAPPED", "UNLINKED_CHILDREN", "RESOLUTION_DROPPED", "AGENTIC_DEGRADED",
    "SOURCE_UNANSWERED",
)
# The typed `reason` a query result carries when it is not a clean answer and not an honest empty.
SHORT_REASONS = ("UNBOUNDED", "PARTIAL_NOT_MATCHED", "UNPUSHED_FILTER", "DISCONNECTED",
                 "INTERNAL_ERROR", "WRITE_IN_PROGRESS", "KILLED", "TOO_EXPENSIVE")
# Public warning codes on a view envelope that mean the same.
SHORT_PUBLIC = ("PARTIAL", "REDUCTION_FAILED", "COMPUTE_FAILED", "PROPERTY_NOT_STORED",
                "AGENTIC_DEGRADED", "RATE_LIMITED", "SOURCE_UNAVAILABLE", "SOURCE_REJECTED",
                "INVALID_FILTER", "UNPUSHED_FILTER", "TOO_BROAD", "FETCH_CAPPED",
                "INDEX_UNAVAILABLE", "ARGUMENT_REFUSED")


def short(d, figure=None):
    tag = "PARTIAL" if figure is None else "PARTIAL %s" % (figure,)
    if not isinstance(d, dict):
        return "REFUSED: not an engine answer: " + str(d)[:160]
    if "outcome" in d or "status" in d:  # a view envelope
        err = d.get("error") or {}
        if d.get("status") != "SUCCEEDED":
            return "REFUSED: %s %s" % (d.get("status"), (err.get("code", "") + " " + err.get("message", "")).strip()[:160] if isinstance(err, dict) else str(err)[:160])
        ws = [w for w in d.get("warnings") or [] if isinstance(w, dict) and w.get("code") in SHORT_PUBLIC]
        if d.get("outcome") not in ("OK", "EMPTY") or ws:
            why = ws[0]["code"] + ": " + ws[0].get("message", "") if ws else "outcome " + str(d.get("outcome"))
            return "%s: %s" % (tag, why[:200])
        return None
    if d.get("error"):
        return "REFUSED: " + str(d["error"])[:160]
    if d.get("run"):
        return "%s: the run had not finished (%s)" % (tag, d["run"])
    ws = [w for w in d.get("warnings") or [] if isinstance(w, str) and w.split(":", 1)[0].strip() in SHORT_CODES]
    if ws:
        return "%s: %s" % (tag, ws[0][:200])
    if d.get("reason") in SHORT_REASONS:
        return "%s: reason %s" % (tag, d["reason"])
    return None


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
    # A partial or refused view is a failed check carrying the engine's reason, never rows to count.
    data = d.get("data") if isinstance(d.get("data"), list) else []
    s = short(d, len(data))
    return (None, s) if s else (data, None)


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
