# Dumping tools (retriever)

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

## Settings

| Setting | Default | |
|---|---|---|
| `keepOriginals` | `true` | Copy the image and logs, leaving the tool's output as it is. Off, they're moved. |
| `removeLeftovers` | `false` | With originals not kept, delete a disc's folder once its image is taken. |
| `settleSeconds` | `120` | How long a dump must be unchanged before it's taken. |

Romdex remembers what it has taken, so a dump kept in place isn't taken again unless it changes.

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
