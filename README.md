# Dumping tools retrieval plugin

Takes finished dumps from the output folders of disc rippers and cartridge dumpers, with the tools' logs. Romdex works
out what each one is from its checksums and files it, and shows the logs to whoever reviews it.

Point it at the folder your tools write to. It looks through every folder under it:

- **a disc:** a folder with a cue sheet or gdi is one dump. It's offered once every track the cue sheet names is there
  and nothing in the folder has changed for `settleSeconds`. Only the image and the logs are taken. Intermediate files
  a ripper leaves, such as redumper's `.scram` and `.state`, stay where they are;
- **cartridges:** in a folder without a cue sheet, each image is a dump of its own. A log or text file with the same
  name goes with it, as cartridge dumpers often write one beside each dump.

Notes are any `.log`, `.txt`, `.dat`, `.md5`, `.sha1` and `.sfv` files that go with a dump. The source Romdex shows
names the tool, when a log mentions one it knows.

It only lists what's finished (**list**), and stages a dump when Romdex asks (**fetch**). It doesn't search: use the
inbox folder plugin for that.

It runs beside [Romdex](https://github.com/Dextrd/Romdex) as a container of its own, which Romdex reaches over the
[retriever contract](https://github.com/Dextrd/Romdex/blob/main/docs/guide/writing-a-retriever-plugin.md).

## Settings

| Setting | Default | |
|---|---|---|
| `keepOriginals` | `true` | Copy the image and logs, leaving the tool's output as it is. Off, they're moved. |
| `removeLeftovers` | `false` | With originals not kept, delete a disc's folder once its image is taken. |
| `settleSeconds` | `120` | How long a dump must be unchanged before it's taken. |

Romdex remembers what it has taken, so a dump kept in place isn't taken again unless it changes.

## Adding it to Romdex

Add this under `services:` in the compose file you run Romdex with, beside `core` and `igir-worker`, so it shares
their `staging` volume:

```yaml
  retriever-dumps:
    image: ghcr.io/dextrd/romdex-retriever-dumps:latest
    container_name: romdex-retriever-dumps
    user: "${PUID:-1000}:${PGID:-1000}"
    restart: unless-stopped
    volumes:
      - staging:/staging
      # Read-only, as it copies by default; make it writable to have dumps moved out.
      - ${DUMPS_PATH:-./dumps}:/dumps:ro
```

`DUMPS_PATH` is the folder your dumping tools write to; set it in the `.env` file beside your compose file, or write the path in its place.

Then start it with `docker compose up -d`. `latest` follows each release; to choose when it changes, use a version
such as `1` or `1.0.0` instead. On SELinux hosts with podman, give it the same `security_opt` as Romdex's own
containers.

Then add `http://retriever-dumps:8080` under Settings → Plugins in Romdex (it's one of the templates under Add). The
plugin makes no network calls.

## Running it

| Variable | Default | |
|---|---|---|
| `DUMPS_ROOT` | `/dumps` | The tools' output folder. |
| `STAGING_ROOT` | `/staging` | The staging volume shared with the core. |
| `PARALLEL_FETCHES` | `2` | Fetches run at once. |

It listens on port 8080 and runs as user 1000. Mount the dumps folder read-only unless `keepOriginals` is off.

## Tests

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```
