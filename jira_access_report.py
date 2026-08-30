"""
Generate a CSV report of users assigned to roles in a Jira Cloud project.

Credentials and Jira site information are loaded from environment variables.
"""

import argparse
import csv
import os
import re
import sys
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth


REQUEST_TIMEOUT_SECONDS = 30
PAGE_SIZE = 50

CSV_COLUMNS = ["project", "role", "access_source", "group", "account_id", "display_name"]


def get_required_environment_variable(name):
    """Return a required environment variable or stop the program."""
    value = os.getenv(name, "").strip()

    if not value:
        raise ValueError(f"Required environment variable {name} is not set.")

    return value


def normalize_jira_url(url):
    """Validate and normalize the Jira base URL."""
    normalized_url = url.strip().rstrip("/")
    parsed_url = urlparse(normalized_url)

    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("JIRA_URL must be a valid HTTPS URL, for example https://example.atlassian.net")

    return normalized_url


def normalize_project_key(project_key):
    """Validate and normalize a Jira project key."""
    normalized_key = project_key.strip().upper()

    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized_key):
        raise ValueError("The project key contains unsupported characters.")

    return normalized_key


def protect_csv_value(value):
    """
    Protect text from being interpreted as a formula by spreadsheet programs.

    Jira names and group names may be opened in Excel or Google Sheets. 
    Values starting with =, +, -, or @ are prefixed with an apostrophe.
    """
    if value is None:
        return ""

    text = str(value)

    if text.startswith(("=", "+", "-", "@")):
        return "'" + text

    return text


class JiraClient:
    """Small Jira Cloud REST API client."""

    def __init__(self, jira_url, email, api_token):
        self.jira_url = normalize_jira_url(jira_url)

        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(email, api_token)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def get_json(self, url, params=None):
        """Perform a GET request and return the decoded JSON response."""
        try:
            response = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as error:
            status_code = error.response.status_code

            print(f"[ERROR] Jira returned HTTP {status_code} for {url}", file=sys.stderr)

            if status_code == 401:
                print("Check the Jira email and API token.", file=sys.stderr)
            elif status_code == 403:
                print("The authenticated user does not have permission to perform this operation.", file=sys.stderr)
            elif status_code == 404:
                print("The requested project, role, group, or endpoint was not found.", file=sys.stderr)

            return None

        except requests.exceptions.Timeout:
            print(f"[ERROR] The request timed out: {url}", file=sys.stderr)
            return None

        except requests.exceptions.RequestException as error:
            print(f"[ERROR] Could not connect to Jira: {error}", file=sys.stderr)
            return None

        except requests.exceptions.JSONDecodeError:
            print(f"[ERROR] Jira returned an invalid JSON response: {url}", file=sys.stderr)
            return None

    def get_project_roles(self, project_key):
        """Return the roles configured for a Jira project."""
        url = f"{self.jira_url}/rest/api/3/project/{project_key}/role"

        return self.get_json(url)

    def get_role_details(self, role_url):
        """Return the actors assigned to a project role."""
        return self.get_json(role_url)

    def get_group_members(self, group_name=None, group_id=None):
        """Return every member of a Jira group using pagination."""
        members = []
        start_at = 0

        if not group_id and not group_name:
            print("[WARNING] A role contains a group without an identifier. Skipping it.", file=sys.stderr)
            return members

        group_label = group_name or group_id
        print(f"Reading group: {group_label}")

        while True:
            parameters = {
                "startAt": start_at,
                "maxResults": PAGE_SIZE,
            }

            if group_id:
                parameters["groupId"] = group_id
            else:
                parameters["groupname"] = group_name

            url = f"{self.jira_url}/rest/api/3/group/member"

            data = self.get_json(url, params=parameters)

            if data is None:
                print(f"[WARNING] Could not read group {group_label}. Skipping it.", file=sys.stderr)
                break

            page_members = data.get("values", [])
            members.extend(page_members)

            if data.get("isLast", True):
                break

            if not page_members:
                print("[WARNING] Jira returned an empty page before the final page.", file=sys.stderr)
                break

            start_at += len(page_members)

        print(f"Found {len(members)} member(s) in {group_label}.")

        return members


def collect_project_users(jira_client, project_key):
    """
    Collect users with direct or group-based project-role access.

    A user may appear more than once when access is obtained through different roles or groups.
    """
    results = []
    seen = set()

    roles = jira_client.get_project_roles(project_key)

    if roles is None:
        return None

    for role_name, role_url in roles.items():
        if role_name == "atlassian-addons-project-access":
            print("Skipping the Atlassian application access role.")
            continue

        print(f"Reading role: {role_name}")

        role_details = jira_client.get_role_details(role_url)

        if role_details is None:
            print(f"[WARNING] Could not read role {role_name}. Skipping it.", file=sys.stderr)
            continue

        for actor in role_details.get("actors", []):
            actor_type = actor.get("type")

            if actor_type == "atlassian-user-role-actor":
                actor_user = actor.get("actorUser", {})
                account_id = actor_user.get("accountId")

                if not account_id:
                    continue

                unique_key = (account_id, role_name, "direct")

                if unique_key in seen:
                    continue

                seen.add(unique_key)

                results.append({
                    "project": project_key,
                    "role": role_name,
                    "access_source": "direct_user",
                    "group": "",
                    "account_id": account_id,
                    "display_name": actor.get(
                        "displayName",
                        "",
                    ),
                })

            elif actor_type == "atlassian-group-role-actor":
                actor_group = actor.get("actorGroup", {})

                group_name = (actor_group.get("displayName") or actor.get("displayName"))

                group_id = actor_group.get("groupId")

                group_members = jira_client.get_group_members(group_name=group_name, group_id=group_id)

                for member in group_members:
                    account_id = member.get("accountId")

                    if not account_id:
                        continue

                    unique_key = (
                        account_id, role_name, group_id or group_name)

                    if unique_key in seen:
                        continue

                    seen.add(unique_key)

                    results.append({
                        "project": project_key,
                        "role": role_name,
                        "access_source": "group",
                        "group": group_name or group_id,
                        "account_id": account_id,
                        "display_name": member.get(
                            "displayName",
                            "",
                        ),
                    })

    return results


def create_unique_report(results):
    """Reduce the complete report to one row per Jira account."""
    unique_results = []
    seen_account_ids = set()

    for record in results:
        account_id = record["account_id"]

        if account_id in seen_account_ids:
            continue

        seen_account_ids.add(account_id)

        unique_results.append({
            "project": record["project"],
            "role": "Multiple/Any",
            "access_source": "See full report",
            "group": "N/A",
            "account_id": account_id,
            "display_name": record["display_name"],
        })

    return unique_results


def write_csv(results, output_file):
    """Write the report to a UTF-8 CSV file."""
    with open(output_file, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)

        writer.writeheader()

        protected_results = [{column: protect_csv_value(record.get(column, "")) for column in CSV_COLUMNS} for record in results]

        writer.writerows(protected_results)


def parse_arguments():
    """Read command-line arguments."""
    parser = argparse.ArgumentParser(description=("Generate a Jira Cloud project-role access report."))

    parser.add_argument("project_key", help="Jira project key, for example DEMO")

    parser.add_argument("--unique", action="store_true", help="Include each Jira account only once.")

    parser.add_argument("--output", help="Optional output CSV filename.")

    return parser.parse_args()


def main():
    """Program entry point."""
    try:
        jira_url = get_required_environment_variable("JIRA_URL")
        jira_email = get_required_environment_variable("JIRA_EMAIL")
        jira_api_token = get_required_environment_variable("JIRA_API_TOKEN")

        arguments = parse_arguments()

        project_key = normalize_project_key(arguments.project_key)

        jira_client = JiraClient(jira_url=jira_url, email=jira_email, api_token=jira_api_token)

        results = collect_project_users(jira_client=jira_client, project_key=project_key)

        if results is None:
            print("[ERROR] The report could not be generated.", file=sys.stderr)
            return 1

        if arguments.unique:
            results = create_unique_report(results)
            default_output = (f"jira_project_unique_users_{project_key}.csv")
        else:
            default_output = (f"jira_project_access_{project_key}.csv")

        output_file = (arguments.output or default_output)

        write_csv(results=results, output_file=output_file)

        print(f"Report generated: {output_file}")
        print(f"Report rows: {len(results)}")

        return 0

    except ValueError as error:
        print(f"[ERROR] {error}", file=sys.stderr)
        return 1

    except KeyboardInterrupt:
        print("\nOperation cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())