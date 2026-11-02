# Contributing

Thanks for helping improve the 7G multi-medium backhaul simulator.

Independent validation evidence is the highest-priority contribution type. A
replication, cross-simulator check, or trace-calibrated model that confirms or
contradicts a claim is more useful than another feature. As of version 0.1.0 the
project has no external issue, pull request, fork contribution, or citation, and
it has not been peer reviewed.

## Development setup

1. Clone the repository.
2. Create a virtual environment.
3. Install requirements:

```bash
pip install -r requirements.txt
```

4. Run the simulator:

```bash
python main.py
```

## Contribution workflow

- Open an issue before significant feature work.
- Keep changes scoped and well tested.
- Update documentation when behavior changes.
- Add or update tests for bug fixes and features.

## Pull requests

- Submit a concise summary of the change.
- Describe how it was validated.
- Include screenshots or output snippets when relevant.

## Validation and replication

- Read [REPLICATION.md](REPLICATION.md) for the exact install, test, benchmark, and validation-tool commands.
- Report a replication attempt with the [replication report template](.github/ISSUE_TEMPLATE/replication_report.yml). Partial and failed replications are welcome when reported honestly.
- Challenge a specific submodel with the [validation challenge template](.github/ISSUE_TEMPLATE/validation_challenge.yml).
- The workflow is: record the commit, run the documented commands, compare results, and state deviations.
- Independent validation evidence is the highest-priority contribution type.

## Issue and pull request templates

- Bug report: [.github/ISSUE_TEMPLATE/bug_report.md](.github/ISSUE_TEMPLATE/bug_report.md)
- Validation challenge: [.github/ISSUE_TEMPLATE/validation_challenge.yml](.github/ISSUE_TEMPLATE/validation_challenge.yml)
- Replication report: [.github/ISSUE_TEMPLATE/replication_report.yml](.github/ISSUE_TEMPLATE/replication_report.yml)
- Pull request checklist: [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)

## Data and claim standards

- Do not fabricate issue numbers, contributor names, citations, downloads, stars, review outcomes, or external usage.
- Record benchmark commands, seeds, units, and software versions with any reported result.
- Keep the GPL-3.0-or-later header on new source files.

## Code style

- Prefer readable Python code.
- Keep comments limited to non-obvious behavior.
- Use small, focused commits.
