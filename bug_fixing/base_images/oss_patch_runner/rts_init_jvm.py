#!/usr/bin/env python3
"""
RTS (Regression Test Selection) initialization script.

This script performs one-time setup for RTS tools (Ekstazi, JcgEks) on Java projects:
- Modifies pom.xml files to add surefire and RTS tool plugins
- Configures surefire settings for RTS compatibility
- Cleans up existing RTS artifacts
- Commits changes to git

Usage:
    python rts_init.py <project_path> [--tool ekstazi|jcgeks]

Environment variables:
    RTS_TOOL: RTS tool to use (ekstazi or jcgeks), default: ekstazi
"""

import os
import sys
import argparse
import subprocess
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional

# RTS tool configurations (only ekstazi and jcgeks supported)
RTS_TOOLS = {
    "ekstazi": {
        "group_id": "org.ekstazi",
        "artifact_id": "ekstazi-maven-plugin",
        "version": "5.3.0",
    },
    "jcgeks": {
        "group_id": "org.jcgeks",
        "artifact_id": "jcgeks-maven-plugin",
        "version": "1.0.0",
    },
}

MAVEN_NAMESPACE = "http://maven.apache.org/POM/4.0.0"
SUREFIRE_VERSION = "2.22.2"

# JcgEks JAR download URLs
JCGEKS_JARS = [
    {
        "url": "https://github.com/acorn421/JcgEks/releases/download/1.0.0/org.jcgeks.core-1.0.0.jar",
        "filename": "org.jcgeks.core-1.0.0.jar",
        "group_id": "org.jcgeks",
        "artifact_id": "org.jcgeks.core",
        "version": "1.0.0",
        "packaging": "jar",
    },
    {
        "url": "https://github.com/acorn421/JcgEks/releases/download/1.0.0/jcgeks-maven-plugin-1.0.0.jar",
        "filename": "jcgeks-maven-plugin-1.0.0.jar",
        "group_id": "org.jcgeks",
        "artifact_id": "jcgeks-maven-plugin",
        "version": "1.0.0",
        "packaging": "maven-plugin",
    },
]


def execute_cmd(cmd: str, cwd: Optional[str] = None, timeout: int = 300) -> bool:
    """Execute a shell command and return success status."""
    try:
        subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"[ERROR] Command failed: {cmd}")
        print(f"[ERROR] {e}")
        return False


def find_maven_executable() -> Optional[str]:
    """
    Find Maven executable in the following order:
    1. $MVN environment variable
    2. mvn in $SRC directory (using find command)
    3. /usr/bin/mvn

    Returns:
        Path to Maven executable, or None if not found
    """
    # 1. Check $MVN environment variable
    mvn_env = os.environ.get("MVN")
    if mvn_env and os.path.isfile(mvn_env) and os.access(mvn_env, os.X_OK):
        print(f"[INFO] Using Maven from $MVN: {mvn_env}")
        return mvn_env

    # 2. Search for mvn in $SRC directory using find command
    src_dir = os.environ.get("SRC", "/src")
    if os.path.isdir(src_dir):
        try:
            result = subprocess.run(
                ["find", src_dir, "-name", "mvn", "-type", "f"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Get the first result that is executable
                for mvn_path in result.stdout.strip().split("\n"):
                    mvn_path = mvn_path.strip()
                    if mvn_path and os.path.isfile(mvn_path) and os.access(mvn_path, os.X_OK):
                        print(f"[INFO] Using Maven from $SRC: {mvn_path}")
                        return mvn_path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 3. Check /usr/bin/mvn
    if os.path.isfile("/usr/bin/mvn") and os.access("/usr/bin/mvn", os.X_OK):
        print("[INFO] Using Maven from /usr/bin/mvn")
        return "/usr/bin/mvn"

    return None


def download_file(url: str, dest_path: str, timeout: int = 120) -> bool:
    """Download a file from URL to destination path."""
    print(f"[INFO] Downloading: {url}")

    # Try wget first
    try:
        result = subprocess.run(
            ["wget", "-q", "-O", dest_path, url],
            timeout=timeout,
            capture_output=True,
        )
        if result.returncode == 0 and os.path.exists(dest_path):
            print(f"[INFO] Downloaded: {dest_path}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback to curl
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", dest_path, url],
            timeout=timeout,
            capture_output=True,
        )
        if result.returncode == 0 and os.path.exists(dest_path):
            print(f"[INFO] Downloaded: {dest_path}")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    print(f"[ERROR] Failed to download: {url}")
    return False


def install_jcgeks_jars() -> bool:
    """
    Download and install JcgEks JAR files to Maven local repository.

    Returns:
        True if installation succeeded, False otherwise
    """
    print("[INFO] Installing JcgEks dependencies...")

    # Find Maven executable
    mvn = find_maven_executable()
    if not mvn:
        print("[ERROR] Maven executable not found!")
        print("[ERROR] Checked: $MVN, $SRC/*/mvn, /usr/bin/mvn, PATH")
        return False

    # Create temp directory for downloads
    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        for jar_info in JCGEKS_JARS:
            jar_path = os.path.join(tmp_dir, jar_info["filename"])

            # Download JAR
            if not download_file(jar_info["url"], jar_path):
                print(f"[ERROR] Failed to download {jar_info['filename']}")
                return False

            # Install to Maven local repository
            install_cmd = [
                mvn,
                "install:install-file",
                f"-Dfile={jar_path}",
                f"-DgroupId={jar_info['group_id']}",
                f"-DartifactId={jar_info['artifact_id']}",
                f"-Dversion={jar_info['version']}",
                f"-Dpackaging={jar_info['packaging']}",
            ]

            print(f"[INFO] Installing {jar_info['artifact_id']}...")
            try:
                result = subprocess.run(
                    install_cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    print(f"[ERROR] Failed to install {jar_info['artifact_id']}")
                    print(f"[ERROR] stdout: {result.stdout}")
                    print(f"[ERROR] stderr: {result.stderr}")
                    return False
                print(f"[INFO] Installed: {jar_info['artifact_id']}")
            except subprocess.TimeoutExpired:
                print(f"[ERROR] Timeout installing {jar_info['artifact_id']}")
                return False

    print("[INFO] JcgEks installation completed!")
    return True


def find_pom_files(project_path: str) -> List[str]:
    """Find all pom.xml files in the project directory."""
    pom_files = []
    for root, _, files in os.walk(project_path):
        for file in files:
            if file == "pom.xml":
                pom_files.append(os.path.join(root, file))
    return pom_files


def get_pom_tree_and_plugins(pom_path: str) -> tuple:
    """Parse pom.xml and return tree and plugins element."""
    tree = ET.parse(pom_path)
    root = tree.getroot()

    ET.register_namespace("", MAVEN_NAMESPACE)
    ns = "{" + MAVEN_NAMESPACE + "}"

    # Find or create build element
    build = root.find(ns + "build")
    if build is None:
        build = ET.Element("build")
        root.append(build)

    # Find or create plugins element
    plugins = build.find(ns + "plugins")
    if plugins is None:
        plugins = ET.Element("plugins")
        build.append(plugins)

    return tree, plugins, ns


def create_plugin_node(group_id: str, artifact_id: str, version: str) -> ET.Element:
    """Create a Maven plugin XML element."""
    plugin = ET.Element("plugin")

    group_elem = ET.SubElement(plugin, "groupId")
    group_elem.text = group_id

    artifact_elem = ET.SubElement(plugin, "artifactId")
    artifact_elem.text = artifact_id

    version_elem = ET.SubElement(plugin, "version")
    version_elem.text = version

    return plugin


def create_surefire_plugin(project_name: str, tool_name: str) -> ET.Element:
    """Create maven-surefire-plugin element with RTS configuration."""
    plugin = create_plugin_node(
        "org.apache.maven.plugins", "maven-surefire-plugin", SUREFIRE_VERSION
    )

    if tool_name != "rtscheck":
        configuration = ET.SubElement(plugin, "configuration")
        excludes_file = ET.SubElement(configuration, "excludesFile")
        # Use unique exclude file path per project and tool
        prefix_path = "${java.io.tmpdir}/" + project_name
        exclude_target = f"_{tool_name}Excludes/"
        excludes_file.text = prefix_path + exclude_target

    return plugin


def create_rts_plugin(tool_name: str) -> ET.Element:
    """Create RTS tool plugin element (Ekstazi or JcgEks)."""
    tool_config = RTS_TOOLS.get(tool_name)
    if not tool_config:
        raise ValueError(f"Unknown RTS tool: {tool_name}")

    plugin = create_plugin_node(
        tool_config["group_id"], tool_config["artifact_id"], tool_config["version"]
    )

    # Add executions
    executions = ET.SubElement(plugin, "executions")
    execution = ET.SubElement(executions, "execution")

    execution_id = ET.SubElement(execution, "id")
    execution_id.text = tool_name

    goals = ET.SubElement(execution, "goals")
    goal_select = ET.SubElement(goals, "goal")
    goal_select.text = "select"
    goal_restore = ET.SubElement(goals, "goal")
    goal_restore.text = "restore"

    return plugin


def delete_surefire_config_element(
    directory: str, target_name: str, replace: Optional[str] = None
) -> None:
    """Delete or replace a surefire configuration element in all pom.xml files."""
    ns = "{" + MAVEN_NAMESPACE + "}"

    for pom_path in find_pom_files(directory):
        try:
            tree = ET.parse(pom_path)
            root = tree.getroot()
            ET.register_namespace("", MAVEN_NAMESPACE)

            modified = False
            plugin_list = root.findall(".//" + ns + "plugin")

            for plugin in plugin_list:
                artifact_id = plugin.find(".//" + ns + "artifactId")
                if artifact_id is not None and artifact_id.text == "maven-surefire-plugin":
                    configuration = plugin.find(".//" + ns + "configuration")
                    if configuration is not None:
                        target = configuration.find(ns + target_name)
                        if target is not None:
                            if replace is None:
                                configuration.remove(target)
                            else:
                                target.text = replace
                            modified = True
                        elif replace is not None:
                            target = ET.SubElement(configuration, target_name)
                            target.text = replace
                            modified = True

            if modified:
                tree.write(pom_path, encoding="utf-8", xml_declaration=True)

        except ET.ParseError as e:
            print(f"[WARNING] Failed to parse {pom_path}: {e}")


def add_rts_plugins_to_pom(pom_path: str, project_name: str, tool_name: str) -> bool:
    """Add surefire and RTS tool plugins to a pom.xml file."""
    try:
        tree, plugins, _ = get_pom_tree_and_plugins(pom_path)

        # Add surefire plugin
        surefire_plugin = create_surefire_plugin(project_name, tool_name)
        plugins.append(surefire_plugin)

        # Add RTS tool plugin
        rts_plugin = create_rts_plugin(tool_name)
        plugins.append(rts_plugin)

        tree.write(pom_path, encoding="utf-8", xml_declaration=True)
        return True

    except Exception as e:
        print(f"[ERROR] Failed to modify {pom_path}: {e}")
        return False


def configure_surefire_settings(project_path: str) -> None:
    """Configure surefire settings for RTS compatibility."""
    # Remove argLine (may conflict with RTS tools)
    delete_surefire_config_element(project_path, "argLine")

    # Set reuseForks=true (required for dependency collection)
    delete_surefire_config_element(project_path, "reuseForks", "true")

    # Set forkCount=1 for consistent behavior
    delete_surefire_config_element(project_path, "forkCount", "1")


def cleanup_rts_artifacts(project_path: str) -> None:
    """Clean up existing RTS artifacts from previous runs."""
    artifacts_to_delete = [".ekstazi", ".jcg", "diffLog"]

    for root, dirs, _ in os.walk(project_path):
        for dir_name in dirs:
            if dir_name in artifacts_to_delete:
                dir_path = os.path.join(root, dir_name)
                try:
                    shutil.rmtree(dir_path)
                    print(f"[INFO] Deleted: {dir_path}")
                except OSError as e:
                    print(f"[WARNING] Failed to delete {dir_path}: {e}")




def git_commit_changes(project_path: str, tool_name: str) -> bool:
    """Commit RTS configuration changes to git."""
    print("[INFO] Committing RTS configuration changes...")

    # Stage all changes
    if not execute_cmd("git add -A", cwd=project_path):
        return False

    # Commit with descriptive message
    commit_msg = f"[RTS] Configure {tool_name} for regression test selection"
    if not execute_cmd(f'git commit -m "{commit_msg}" --allow-empty', cwd=project_path):
        return False

    print(f"[INFO] Changes committed: {commit_msg}")
    return True


def init_rts(project_path: str, tool_name: str) -> bool:
    """
    Initialize RTS tool configuration for a Java project.

    Args:
        project_path: Path to the Java project root
        tool_name: RTS tool to use (ekstazi or jcgeks)

    Returns:
        True if initialization succeeded, False otherwise
    """
    project_path = os.path.abspath(project_path)
    project_name = os.path.basename(project_path.rstrip("/"))

    print(f"[INFO] Initializing RTS ({tool_name}) for project: {project_name}")
    print(f"[INFO] Project path: {project_path}")

    # Validate tool name
    if tool_name not in RTS_TOOLS:
        print(f"[ERROR] Unknown RTS tool: {tool_name}")
        print(f"[ERROR] Available tools: {list(RTS_TOOLS.keys())}")
        return False

    # Find all pom.xml files
    pom_files = find_pom_files(project_path)
    if not pom_files:
        print("[ERROR] No pom.xml files found in project")
        return False

    print(f"[INFO] Found {len(pom_files)} pom.xml file(s)")

    # Step 1: Clean up existing RTS artifacts (but keep build artifacts)
    print("[INFO] Step 1: Cleaning up existing RTS artifacts...")
    cleanup_rts_artifacts(project_path)

    # Step 2: Install JcgEks JARs if using jcgeks tool
    if tool_name == "jcgeks":
        print("[INFO] Step 2: Installing JcgEks dependencies...")
        if not install_jcgeks_jars():
            print("[ERROR] Failed to install JcgEks dependencies")
            return False
    else:
        print("[INFO] Step 2: Skipping JcgEks installation (using ekstazi)")

    # Step 3: Add RTS plugins to all pom.xml files
    print("[INFO] Step 3: Adding RTS plugins to pom.xml files...")
    for pom_path in pom_files:
        if add_rts_plugins_to_pom(pom_path, project_name, tool_name):
            print(f"[INFO] Modified: {pom_path}")
        else:
            print(f"[WARNING] Failed to modify: {pom_path}")

    # Step 4: Configure surefire settings
    print("[INFO] Step 4: Configuring surefire settings...")
    configure_surefire_settings(project_path)

    # Step 5: Commit changes to git
    print("[INFO] Step 5: Committing changes to git...")
    git_commit_changes(project_path, tool_name)

    print("[INFO] RTS initialization completed successfully!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Initialize RTS (Regression Test Selection) for Java projects"
    )
    parser.add_argument("project_path", help="Path to the Java project root")
    parser.add_argument(
        "--tool",
        choices=list(RTS_TOOLS.keys()),
        default=os.environ.get("RTS_TOOL", "ekstazi"),
        help="RTS tool to use (default: ekstazi or RTS_TOOL env var)",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.project_path):
        print(f"[ERROR] Project path does not exist: {args.project_path}")
        sys.exit(1)

    success = init_rts(args.project_path, args.tool)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
