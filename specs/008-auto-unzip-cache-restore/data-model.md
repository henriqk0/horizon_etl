# Data Model & Domain Entities: Export ZIP Cache Bootstrapping

## Transient Structures

### 1. ExportArchiveInfo

Represents a discovered export ZIP archive candidate during discovery.

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `path` | `Path` | Absolute path to the candidate ZIP archive file. |
| `filename` | `str` | Name of the ZIP archive file. |
| `mtime` | `float` | Modification timestamp used for sorting candidates. |
| `size_bytes` | `int` | Total size of the archive in bytes. |

### 2. BootstrapResult

Represents the execution outcome of the cache bootstrap operation.

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `restored` | `bool` | `True` if a valid archive was decompressed; `False` if skipped or no archive found. |
| `archive_used` | `str \| None` | Path to the ZIP archive that was extracted, or `None`. |
| `files_extracted` | `int` | Number of files extracted into `data/exports/`. |
| `warning` | `str \| None` | Warning or informational message if no archive found or minor errors occurred. |

## Disk Layout & Schema

### Restored Export Directory (`data/exports/`)

```text
data/exports/
├── project_sigpesq_files_json/   # Restored Mistral AI project JSON reports (e.g. PJ_1058.json)
├── initiatives_canonical.json    # Restored canonical initiatives
├── researchers_canonical.json    # Restored canonical researchers
├── advisorships_canonical.json    # Restored canonical advisorships
├── *_graph.json                  # Restored collaboration & relationship graphs
└── *_manifest.json               # Restored subgraph manifests
```
