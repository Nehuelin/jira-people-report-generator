# Jira Project Access Report

A Python command-line tool that generates a CSV wit data of users assigned to roles in a Jira Cloud project.

The report includes users assigned directly to a project role and users who receive access through a Jira group.

This utility provides a convenient way to export project-role assignments and group-derived membership to CSV when that view is not readily available in the desired reporting format.

## Features

* Reads all roles associated with a Jira Cloud project
* Identifies direct user assignments
* Expands group assignments using Jira API pagination
* Avoids duplicate role/group entries
* Supports a complete access report or a unique-user report
* Exports results as a UTF-8 CSV file
* Loads Jira credentials from environment variables
* Protects CSV output from spreadsheet-formula injection

## Requirements

* Python 3.10 or newer
* A Jira Cloud account
* A Jira API token
* Permission to view the target project, roles, users, and groups

Install the dependency with:

```bash
pip install -r requirements.txt
```

## Jira API token

Create an API token from your Atlassian account security settings:

https://id.atlassian.com/manage-profile/security/api-tokens

Treat the token like a password. Never commit it to GitHub or include it directly in the script.

## Environment variables

The program requires three environment variables:

* `JIRA_URL`: Jira Cloud site URL
* `JIRA_EMAIL`: email associated with the Atlassian account
* `JIRA_API_TOKEN`: Atlassian API token

Example Jira URL:

```text
https://example.atlassian.net
```

### Windows PowerShell

```powershell
$env:JIRA_URL="https://example.atlassian.net"
$env:JIRA_EMAIL="your-user@example.test"
$env:JIRA_API_TOKEN="your-api-token"
```

These variables apply to the current PowerShell session.

### macOS or Linux

```bash
export JIRA_URL="https://example.atlassian.net"
export JIRA_EMAIL="your-user@example.test"
export JIRA_API_TOKEN="your-api-token"
```

## Usage

Generate the complete access report:

```bash
python jira_access_report.py DEMO
```

Replace `DEMO` with the target Jira project key.

Generate a report containing each Jira account only once:

```bash
python jira_access_report.py DEMO --unique
```

Choose a custom output filename:

```bash
python jira_access_report.py DEMO --output report.csv
```

Options can be combined:

```bash
python jira_access_report.py DEMO --unique --output unique-users.csv
```

## Output

The complete report contains the following columns:

| Column          | Description                                                |
| --------------- | ---------------------------------------------------------- |
| `project`       | Jira project key                                           |
| `role`          | Project role through which access was found                |
| `access_source` | Whether the assignment is direct or group-based            |
| `group`         | Jira group responsible for the assignment, when applicable |
| `account_id`    | Jira Cloud account identifier                              |
| `display_name`  | User display name                                          |

A user can appear multiple times in the complete report when assigned through multiple roles or groups.

The `--unique` option generates one row per Jira account. Because the report is deduplicated, it does not preserve every role and group relationship.

## Required Jira permissions

Results depend on the permissions of the authenticated Jira account. The account may require permission to:

* Browse the target project
* View project roles
* Browse users and groups
* Access group membership information

A successful API response does not guarantee that the account can see every user if the Jira site applies additional privacy or administrative restrictions.

## Privacy and responsible use

The generated report may contain personal or organization-sensitive information, including display names, account identifiers, group names, and project-access relationships.

Before generating, storing, or sharing a report:

* Confirm that you are authorized to access the information.
* Store reports only in an approved location.
* Do not commit generated reports to GitHub.
* Follow the applicable organization’s retention and access-control policies.

This repository contains no real Jira URL, credentials, organization names, project keys, groups, or user information.

## Limitations

* Jira commonly hides email addresses due to privacy settings.
* The report covers actors assigned through Jira project roles.
* It does not prove every possible source of effective Jira permissions.
* Permission schemes, issue security, application access, product access, and administrative privileges may affect effective access separately.
* Group membership visibility depends on the authenticated account’s permissions.

Therefore, the output should be described as a **project-role assignment report**, not a complete authorization audit.