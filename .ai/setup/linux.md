# Linux / macOS setup

```bash
git clone https://github.com/PlayTalk-ir/bale-adapter.git
cd bale-adapter
chmod +x scripts/bootstrap-local.sh scripts/ensure-uv.sh
./scripts/bootstrap-local.sh
```

Later:

```bash
source scripts/activate.sh
```

Skip login on re-run: `./scripts/bootstrap-local.sh --skip-login`
