# Team Workflow

## Branches

- `main` is the stable integration branch.
- `trijal`, `hardik`, `gayatri`, and `prashant` are individual working branches.
- Each member should commit only to their own branch and open a pull request into
  `main` when ready.

## Daily Start

```bash
git checkout trijal
git pull origin trijal
docker compose up --build -d
```

Replace `trijal` with your own branch name when another member works.

## Daily Stop

```bash
docker compose down
wsl --shutdown
```

Use `wsl --shutdown` only after Docker Desktop is closed or after the Docker
containers are stopped.

## Before Pushing

```bash
python -m pytest
git status
git add .
git commit -m "Describe the change"
git push origin trijal
```

## Pull Request Rule

Open a pull request from your branch into `main`. Do not merge directly into
`main` unless the team has reviewed the changes.
