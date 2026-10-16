# Windows Filesystem Security Review Package

Purpose: independent review of the existing offline evidence readers. This package is not a security approval, does not authorize live capture, and does not authorize production integration. Phase 25 remains the broader readiness and search-page validation plan; this document focuses on the Windows filesystem question.

## Scope and review request

Review `search_page_evidence.py` and `offline_search_evidence.py` for safe reading of explicitly supplied files beneath a trusted artifact root on the supported Windows/filesystem configurations. Do not assume a particular Windows API is suitable based on symbol availability. The reviewer should provide a written design decision, supported environment, documented API contract, limitations, and real-platform test results. If any required guarantee cannot be established, the operation must be rejected on that environment.

## Threat-model facts the project owner must supply

The source confirms that callers supply `artifact_root`, `metadata_path`, and optionally `screenshot_path`; it does not establish who controls those values or who can modify the root or its parent directories. Before the specialist decides whether the design is safe, the project owner must state:

- whether evidence files or path values can come from an untrusted user or process;
- which users/processes can create, replace, rename, or change permissions on the artifact root, its parent directories, and the evidence files, including concurrent processes running as the same account;
- whether the root is local or may reside on a network, removable, synchronized, or otherwise non-local filesystem;
- the expected privilege level and whether symlink/junction creation is available in the deployment environment;
- whether concurrent mutation is in scope and, if so, which attacker capabilities the reader must resist.

These facts are currently **unknown**. The specialist should not infer a weaker attacker model from the current path checks or bounded reads. If the project owner cannot define or enforce the required trust boundary, the reviewer should recommend rejecting artifact reads for that deployment.

### Owner-provided deployment assumptions (not independently verified)

The owner states that the intended deployment is one personal Windows 11 computer using local storage; evidence files are created and trusted by the owner; no concurrent modification is expected; and the reader must fail closed whenever a file cannot be verified. These statements narrow the intended use case, but are owner-provided assumptions rather than verified system facts. They do not prove that malicious inputs, unexpected software, concurrent same-account processes, path replacement, or filesystem races are impossible.

The following deployment details remain **UNKNOWN** and must not be inferred from those assumptions:

- The exact supported Windows 11 release/build and Python runtime for deployment. The Windows/Python/filesystem support matrix remains to be specified.
- The actual trusted artifact-root path, its owner, and permissions on the root and every parent directory.
- The actual filesystem type used by the artifact root. “Local storage” does not identify a filesystem or its relevant semantics.
- Whether another process running as the same account, or unexpected software, can replace, rename, or modify the root or evidence files while they are read.
- Whether the deployed filesystem and permissions permit symbolic links, junctions, mount points, or other relevant reparse points in the root or any path component.
- Whether artifacts can be placed on removable, synchronized, virtualized, or filter-mediated storage despite the local-storage assumption.
- Whether the existing 256 KiB metadata and 10 MiB screenshot limits meet the owner's requirements.

The specialist should evaluate the reader against this stated single-user/local-storage use case only after these unknowns are answered or explicitly constrained. “No expected concurrent modification” is not a guarantee that concurrent modification cannot occur; replacement and mutation cases in the acceptance matrix therefore remain required unless the owner and reviewer document a justified, enforceable exclusion.

## Source-confirmed behavior

### `search_page_evidence.py`

`_check_screenshot()` validates a relative reference and digest (`search_page_evidence.py:188–203`), resolves the root and target (`:208–212`), stats the resolved target for regular-file mode and the 10 MiB limit (`:214–220`), then separately opens that path (`:222–225`). It reads in bounded chunks up to the limit plus one byte (`:225–238`), compares bytes read with the earlier stat size (`:239–241`), and compares SHA-256 with the supplied digest (`:242–247`). Errors become validation issues (`:243–245`).

### `offline_search_evidence.py`

`_resolve_under_root()` constructs/resolves a path, checks it is under the supplied root, checks `is_file()`, and returns a path (`offline_search_evidence.py:51–62`). `_read_metadata()` stats the path for regular-file mode and the 256 KiB bound (`:65–69`), separately opens it and reads at most limit plus one (`:70–79`). `_relative_reference()` rejects unsafe/absolute/traversal references, resolves the target, and checks containment and file status (`:86–100`). `_hash_png()` stats for regular-file mode and the 10 MiB bound (`:103–108`), separately opens, checks the PNG signature, reads/hash-bounds the data, and checks the final byte count against the earlier stat size (`:109–128`). `prepare_evidence_candidate()` resolves the caller-supplied root and metadata path before reading metadata (`:150–170`) and requires an explicit screenshot path when metadata declares one (`:172–176`).

### Existing safeguards and tests

The readers use strict resolution in the offline wrapper, containment checks, regular-file checks, bounded reads, PNG signature validation, and byte/hash consistency checks. Existing tests cover traversal, hash mismatch, size limits/growth via mocks, and symlink escape when symlink creation is supported (`tests/test_search_page_evidence.py:284–384`; `tests/test_offline_search_evidence.py:150–214, 254–291`). These tests do not establish Windows kernel behavior for reparse points, object identity, or replacement races.

## Facts, risks, assumptions, and open questions

| Topic | Confirmed from source | Potential risk (not proof of exploitability) | Assumption / specialist question | Evidence needed |
|---|---|---|---|---|
| Trusted root | Callers provide `artifact_root`; code resolves it and compares resolved paths. | A path comparison does not itself bind later opens to that directory object. | How is the root established and protected from replacement/reparse traversal? | Documented supported API contract and real-platform test. |
| Check/stat/open sequence | Resolution/containment and stat precede a separate path-based open in both readers. | A path component or file may change between check/stat and open. | Can a supported user-mode method open relative to the trusted root and bind validation to that opened object? | Replacement-before/during-open tests; handle identity evidence. |
| Reparse points | Source uses path resolution and containment; no explicit reparse-tag walk/rejection is present in these sequences. | Symlink, junction, mount-point, or other reparse traversal may affect the resolved/opened object, including intermediate components. | Which tags and path components are covered on each supported filesystem? | File/directory link, junction, mount-point, and intermediate-component tests. |
| Identity/type/size | Type and size are checked through path-based `stat`; bytes are later read through a separate open. | The checked metadata may not describe the opened object. Size equality cannot detect same-size content replacement. | How can identity, regular-file type, and size be verified on the same opened object that is read? | Handle-based identity/type/size checks plus replacement and mutation tests. |
| Bounded read/hash | Reads have explicit limits and compute SHA-256 from bytes read. | Bounded allocation does not establish containment, authenticity, or an immutable snapshot. | What consistency guarantee is required if contents mutate during reading? | Growth and same-size mutation tests; fail-closed digest/identity criteria. |
| Environment | Repository evidence does not establish supported Windows releases, filesystems, or privileges for these readers. | Behavior may differ by Windows release, filesystem, reparse type, or privilege. | What exact OS/filesystem combinations are supported? | Written support matrix and tests on each required environment. |
| Failures | Reader errors are converted to validation failure/issues. | An unsupported or ambiguous platform must not silently fall back to weaker path-based access. | Which errors reject input, and which environments must disable artifact reading? | Permission, missing-file, unsupported-API/filesystem tests and documented fail-closed behavior. |

## Questions requiring the specialist's written answer

1. What Windows versions, filesystem types, and privilege levels are in scope?
2. What documented, application-supported user-mode API contract establishes a trusted root handle and opens a child file relative to it?
3. Does that contract prevent traversal through every intermediate component and the final component when they are symbolic links, junctions, mount points, or other reparse tags? If not, which cases are unsupported and rejected?
4. How are root identity and containment established without relying on string-prefix comparisons or final-component-only checks?
5. How are file identity, regular-file type, and size obtained from the same opened object that supplies the bytes?
6. What does the API guarantee under replacement before/during open, and what races remain?
7. What consistency can be promised for bounded reading and hashing under concurrent growth or same-size mutation?
8. How are access denial, missing files, unsupported API/filesystem behavior, and unexpected reparse tags handled? Is every such case fail-closed?
9. Which guarantees are documented API behavior, which depend on filesystem implementation, and which require deployment restrictions?

Do not accept native API export availability, normalized full-path strings, path-prefix checks, or final-component-only checks as proof of the required contract without authoritative documentation and environment-specific validation. No API recommendation is made by this package.

## Official API documentation findings for specialist review

These findings narrow the API question, but do not establish an approved reader design.

- Microsoft documents `OBJECT_ATTRIBUTES.RootDirectory` as allowing an object name relative to a directory handle. The same structure documents `OBJ_DONT_REPARSE`: no reparse points are followed while parsing the associated object name; encountering one fails with `STATUS_REPARSE_POINT_ENCOUNTERED`. This wording covers name parsing, but the project still needs confirmation that this flag is supported in the exact user-mode file-open call and on each supported filesystem. [OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)
- The user-mode [`NtCreateFile`](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile) page documents `RootDirectory`-relative names and `FILE_OPEN_REPARSE_POINT` behavior. However, its `ObjectAttributes.Attributes` member description says the value can be zero or `OBJ_CASE_INSENSITIVE`; it does not list `OBJ_DONT_REPARSE`. This is a documentation gap against the generic `OBJECT_ATTRIBUTES` contract. A Windows specialist or Microsoft support must resolve whether the exact user-mode `NtCreateFile` call may rely on `OBJ_DONT_REPARSE`, including version and filesystem scope. Do not infer support from the flag's declaration or export availability.
- [`CreateFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew) documents `FILE_FLAG_OPEN_REPARSE_POINT` and says an opened symbolic-link leaf yields a handle to the link itself. That is a leaf behavior; the documented API does not provide a root-directory-relative name parameter. It does not by itself establish containment across a multi-component path.
- [`GetFileInformationByHandleEx`](https://learn.microsoft.com/en-us/windows/desktop/api/winbase/nf-winbase-getfileinformationbyhandleex) retrieves information for the supplied handle, including `FileStandardInfo`, `FileAttributeTagInfo`, and `FileIdInfo` classes. This can support same-handle metadata checks, subject to provider/filesystem support. Microsoft's [`BY_HANDLE_FILE_INFORMATION`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information) documentation warns that file IDs are filesystem-specific, can be reused over time, and may change in some cases; identifiers do not independently prove containment or immutable contents.
- [`GetFinalPathNameByHandleW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew) returns a resolved final path and offers DOS, volume-GUID, and NT naming forms. Its documentation describes alias and SMB limitations. A returned path string is not a substitute for a documented no-reparse, root-relative open contract.

The Python 3.12 [`Path.resolve()`](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.resolve) contract resolves symlinks and normalizes `..`; it does not bind a subsequent separate `open()` to the checked object. The repository uses this operation before path-based opens, as detailed above.

### Current environment versus supported environment

Observed for this inspection: Python 3.12.14 (64-bit), Windows 11 build 26200, and the project is on the C: volume reported as NTFS. The repository does not declare a supported Windows-version or filesystem matrix. These local facts are not a support policy and do not establish behavior on other releases, ReFS, FAT/exFAT, SMB, cloud/sync providers, or third-party filters. The owner must define the deployment matrix before implementation review.

### Updated specialist decision required

The specialist should assess the exact documented contract for a directory-relative user-mode open with `OBJ_DONT_REPARSE`, not merely whether a test call succeeds. Resolve the `NtCreateFile`/`OBJECT_ATTRIBUTES` documentation mismatch; state which intermediate and final reparse tags are rejected; explain how a trusted root handle is established; and state what same-handle metadata and read guarantees apply for each supported filesystem. If that contract cannot be established for a supported environment, artifact reading remains disabled there. No source-code security fix or independent approval is claimed by adding these references.

## Acceptance test matrix

All real-filesystem cases require a dedicated Windows test environment using each supported OS/filesystem combination. Expected result is either safe access to the exact in-root object under the specialist-approved contract or a controlled rejection; no weaker fallback is acceptable.

| Case | Required test | Acceptance criterion |
|---|---|---|
| Normal files | Read in-root JSON and PNG files. | Type, identity, size, bounded bytes, and digest correspond to the same opened object. |
| Traversal | Relative `..`, absolute paths, and alternate path forms escaping the root. | Reject without reading outside the root. |
| Reparse escape | File and directory symlinks, junctions, mount points, and other relevant reparse tags. | Reject or prove the documented safe in-root resolution; never read an outside object. |
| Intermediate component | Place/replace a reparse point in each intermediate path component. | Reject or establish containment under the specialist-approved contract. |
| Replacement before/during open | Replace the target and an intermediate directory between resolution, validation, and opening. Include same-size replacement. | Read the validated object or reject; never accept a different unvalidated object. |
| Growth during read | Grow metadata/PNG after initial size observation beyond 256 KiB/10 MiB. | Bounded allocation; reject on limit/consistency violation. |
| Same-size mutation | Change content without changing size while reading. | Meet the documented snapshot/identity guarantee or reject; matching length alone is insufficient. |
| Non-regular files | Directory, device, and other non-regular targets. | Reject before treating input as evidence. |
| Missing/permissions | Missing target, access denied, insufficient directory/file permissions. | Controlled fail-closed result; no candidate accepted. |
| Unsupported environment | Unsupported filesystem, OS, API, or required privilege unavailable. | Explicitly reject/disable artifact reading; no path-based fallback. |

Mocks may verify bounded chunk requests, hash calculation over returned bytes, API call ordering, error mapping, and that failure produces no candidate. Mocks cannot establish reparse traversal behavior, handle identity, atomic open semantics, or Windows race guarantees.

## Reviewer decision checklist

- [ ] Supported Windows releases, filesystems, and privilege assumptions are named.
- [ ] Trusted-root establishment and child-open guarantees are supported by authoritative documentation.
- [ ] Intermediate and final reparse behavior is addressed for relevant tags.
- [ ] Identity, type, size, bounded read, and hash apply to the same opened object.
- [ ] Replacement, growth, and same-size mutation guarantees are explicit.
- [ ] Real-platform tests pass for every supported environment, or unsupported cases are rejected.
- [ ] Access-denied and unsupported conditions fail closed.
- [ ] Remaining limitations are documented and accepted by the project owner before implementation review.

## Decision record

Reviewer: ____________________  Date: ____________________

Supported OS/filesystems: ______________________________________________

Documented API contract and references: __________________________________

Unresolved limitations / rejected environments: __________________________

Decision: [ ] acceptable for separate implementation review  [ ] not acceptable

This sign-off section is blank. No independent review or approval is claimed. Until completed and accepted, do not change the readers to use a speculative workaround, do not use them as a security boundary for externally supplied artifacts, and do not connect artifact reading to `dom_evidence_package.py` or production collection/publication.
