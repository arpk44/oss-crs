# Fix Java Incremental Build Command

Fix Java Maven project build.sh and test.sh scripts for incremental builds and RTS (Regression Test Selection).

> **IMPORTANT:** This command uses the `java-rts-build-converter` skill. **YOU MUST invoke the skill** to get the correct patterns and guidelines before making any modifications.

## Quick Start

Given a log directory from Java incremental build tests and an oss-fuzz directory, analyze errors and fix the build.sh/test.sh scripts or pom.xml files.

## Instructions

### Step 1: Invoke the Skill (REQUIRED)

**Before analyzing logs or making any changes, invoke the `java-rts-build-converter` skill:**

```
Use the Skill tool with skill: "java-rts-build-converter"
```

The skill provides:
- Two-level exclusion strategy (excludesList vs EXCLUDE_TESTS)
- OpenClover instrumentation failure patterns
- Maven multi-module inheritance rules
- Correct pom.xml locations for test exclusions
- Standard test.sh template
- Common error patterns and solutions

### Step 2: Analyze Logs

1. Read `summary.txt` in the log directory
2. Identify failed projects and specific test failures
3. Read individual log files for error details

```bash
# Find test failures
grep -E "<<< FAILURE!|<<< ERROR!" <logfile>
grep -oP "(?<=FAILURE! - in )[a-zA-Z0-9_.]+" <logfile> | sort -u
```

### Step 3: Find Test Locations

**CRITICAL: Find ALL locations where the failing test exists**

```bash
# Example: find HtmlParserTest
find . -name "HtmlParserTest.java" -type f
```

If test exists in multiple modules, you must fix each module's pom.xml.

### Step 4: Apply Fixes Using Skill Patterns

Key principles:
- **Parent `<plugins>` NOT inherited** - Must add excludes to child module's pom.xml
- **Check existing surefire config** - Merge, don't replace
- **Multiple locations** - Fix ALL modules where test exists

**Example Fix - Add to child module's pom.xml:**

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <excludes>
          <exclude>**/HtmlParserTest.java</exclude>
        </excludes>
      </configuration>
    </plugin>
  </plugins>
</build>
```

### Step 5: Test the Fixes Using Subagent

**CRITICAL: Use the `test-inc-build` subagent via Task tool instead of running uv run directly.**

**Single project test:**
```
Task tool:
  subagent_type: "test-inc-build"
  description: "Test incremental build"
  prompt: "Run incremental build test for aixcc/jvm/{project_name} with oss-fuzz path ../oss-fuzz"
```

**For multiple projects, launch parallel subagents in a single message:**
```
Task tool (run_in_background: true):
  subagent_type: "test-inc-build"
  prompt: "Run incremental build test for aixcc/jvm/atlanta-tika-delta-01 with oss-fuzz path ../oss-fuzz"

Task tool (run_in_background: true):
  subagent_type: "test-inc-build"
  prompt: "Run incremental build test for aixcc/jvm/atlanta-jackson-delta-01 with oss-fuzz path ../oss-fuzz"

Then use TaskOutput to retrieve results from each agent.
```

## Common Fix Patterns

### Pattern 1: Skip Test in Specific Module

When test exists in `tika-parser-html-module`:

**File:** `tika-parsers/tika-parsers-standard/tika-parsers-standard-modules/tika-parser-html-module/pom.xml`

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <configuration>
        <excludes>
          <exclude>**/HtmlParserTest.java</exclude>
        </excludes>
      </configuration>
    </plugin>
  </plugins>
</build>
```

### Pattern 2: Skip via Command Line (test.sh)

```bash
# In test.sh
mvn test -Dsurefire.excludes="**/HtmlParserTest.java,**/OtherTest.java"
```

### Pattern 3: Merge with Existing Surefire Config

```xml
<!-- If module already has surefire config, ADD excludes -->
<plugin>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>-Xmx4g</argLine>
    <!-- ADD THIS -->
    <excludes>
      <exclude>**/FailingTest.java</exclude>
    </excludes>
  </configuration>
</plugin>
```

### Pattern 4: Multiple Modules with Same Test

If `HtmlParserTest.java` exists in both:
- `tika-parser-html-module/`
- `tika-parsers-standard-package/`

You must add excludes to BOTH pom.xml files.

### Pattern 5: OpenClover RTS Test Exclusion

**CRITICAL:** `maven.clover.excludesList` only excludes instrumentation, NOT test execution!

```bash
# WRONG - Tests still run!
-Dmaven.clover.excludesList="**/ServerIdTest.java"

# CORRECT - Tests excluded from running
-Dmaven.clover.optimizeExcludes="**/ServerIdTest.java,**/ZKUtilTest.java"
```

See the `java-rts-build-converter` skill for detailed OpenClover configuration.

## Why Parent pom.xml Excludes Don't Work

```
tika-parent/pom.xml
├── <pluginManagement>  → Inherited when child DECLARES plugin
│   └── <plugins>
└── <plugins>           → NOT inherited (parent only)
        └── maven-surefire-plugin
            └── <excludes>
                └── **/HtmlParserTest.java  ← Does NOT apply to children!
```

**Solution:** Add exclude to the actual module's pom.xml where test runs.

## Input Required

Provide:
1. Log directory path (optional)
2. OSS-Fuzz directory path
3. Project name - e.g., "aixcc/jvm/atlanta-tika-delta-01"
4. Specific test to skip (optional)

$ARGUMENTS
