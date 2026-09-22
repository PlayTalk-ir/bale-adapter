# Windows setup

## One line (recommended)

```powershell
irm https://raw.githubusercontent.com/PlayTalk-ir/bale-adapter/master/scripts/install-windows.ps1 | iex
```

Installs Git, clones to `%USERPROFILE%\bale-adapter`, runs uv + bootstrap + login.

## Manual

```powershell
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
. .\scripts\bootstrap.ps1
```

Dot-source (`. .\`) keeps venv active in the shell.

## Policy blocked?

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Phone formats

| Input | Normalized |
|-------|------------|
| `09924466793` | `989924466793` |
| `+989924466793` | `989924466793` |

## Later sessions

```powershell
cd $HOME\bale-adapter
. .\scripts\activate.ps1
```
