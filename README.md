# realm-java-source-code

The source a Java jar was compiled from, reached from what
[realm-java-code](https://github.com/embabel-worlds/realm-java-code) finds in the jar. Install both;
this realm only adds edges from realm-java-code's types into source, and realm-java-code works
without it.

```cypher
MATCH (j:Jar {path: 'data/jars/spring-core-6.2.18.jar'})-[:HAS_METHOD]->
      (m:JavaMethod {owner: 'org.springframework.util.StringUtils', name: 'hasText'})-[:DECLARED_AT]->(d:JavaDeclaration)
RETURN m.key, d.javadoc, d.text
```

Source is read where it is, by the appliance's `source` producer kind, when a query reaches it.
Nothing is ingested or stored.

## Where the source can be

For a jar, in order:

1. `<jar name>-sources.jar` beside the jar (the Maven convention; nothing to configure);
2. `<jar name>-sources.jar` in `data/src/` of the world, or this realm's `data/sources/`;
3. a checkout mounted or cloned anywhere under the world's `data/src/` — any module layout;
   `org/x/Cache.java` is found under `core/src/main/java/` or wherever the build keeps it;
4. a git repository at a commit, added as a root in `producers/source.yml`:
   `{ git: "https://github.com/<owner>/<repo>", ref: "v{version}" }`. `{version}` is the jar's
   version; a tag or branch is resolved to its commit, which rows report, with a link to the line.

A jar for which no source is found answers everything realm-java-code answers, and a warning says
no source was found. When source is found but is another version, spans say so: `matches: false`
means the name the jar expects is not on those lines.

## The graph

See `types/source.yml`. JavaType ─DEFINED_IN▶ JavaSource ─DECLARES▶ JavaDeclaration; JavaMethod,
JavaMethodCall and JavaFieldAccess ─SOURCE_AT▶ SourceSpan; JavaMethod ─DECLARED_AT▶ JavaDeclaration;
JavaMethodCall ─AT_SITE▶ JavaCallSite; JavaSource ─DECLARES_LOCAL▶ JavaLocal and JavaMethod
─HAS_LOCAL▶ JavaLocal. JavaSource, JavaDeclaration, JavaCallSite and JavaLocal are the Java children
of the standard model's `Source`, `SourceDeclaration`, `CallSite` and `SourceLocal`.

Declarations and call sites come from a Java file's syntax tree, parsed on demand. A call site's
argument types are resolved from the file alone (`new X(…)`, literals, casts, parameters, locals,
fields); a type only another file could explain is left as written and marked unresolved. A local
says whether `var` is legal for it and whether `var` would keep its declared type, by the same rules.

Views that read the whole jar's source: `JavaLongestMethods` (the longest methods by the lines their
declarations span) and `JavaExplicitLocalsVarWouldKeep` (methods declaring `String s = "x"` where
`var s` would keep the type).

## Example

Ships `data/sources/spring-core-6.2.18-sources.jar` (Apache-2.0, from Maven Central), the sources
of realm-java-code's example jar, with four demo views over it.
