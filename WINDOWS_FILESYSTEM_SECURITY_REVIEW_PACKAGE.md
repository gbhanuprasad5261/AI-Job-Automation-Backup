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

### Python 3.12 Windows constraints verified from the API documentation

- Python 3.12 documents `dir_fd` support as Unix-only; `dir_fd` parameters do not work on Windows. Do not treat a POSIX `openat`-style design expressed through `os.open(..., dir_fd=...)` as available for this Windows deployment. The runtime’s `os.supports_dir_fd` is the relevant per-function capability set, but the documented Windows limitation is categorical.
- `Path.stat()` follows symlinks by default. `Path.is_file()` accepts a symlink to a regular file, and `Path.is_junction()` (added in Python 3.12) answers a path query for junctions. These helpers do not bind the later open to the checked path, do not reject all reparse tags, and do not by themselves close replacement races.
- `os.fstat(fd)` is documented as querying the file descriptor, but this review does not infer from that description that every required Windows identity, reparse-tag, type, and size property is available through the CPython file object on every supported filesystem. If proposed, document and test the exact Windows handle/descriptor mapping and queried fields. The Win32 `GetFileInformationByHandleEx` API explicitly takes a handle and lists `FileStandardInfo`, `FileAttributeTagInfo`, and `FileIdInfo`; returned information remains subject to OS/provider/filesystem support.
- Microsoft documents `OBJECT_ATTRIBUTES.RootDirectory` as a directory-relative name and `OBJ_DONT_REPARSE` as rejecting reparse traversal while parsing. The `NtCreateFile` page, however, documents `ObjectAttributes.Attributes` as zero or `OBJ_CASE_INSENSITIVE` and does not list `OBJ_DONT_REPARSE`. This documentation mismatch remains unresolved for the exact user-mode call and supported OS/filesystem set; this package does not approve relying on that flag.
- `CreateFileW` documents `FILE_FLAG_OPEN_REPARSE_POINT` behavior for opening the leaf reparse point itself, but its documented interface has no root-directory-relative parameter. That leaf behavior alone does not establish containment across intermediate path components. `GetFinalPathNameByHandleW` returns a resolved path string and has naming/SMB limitations; final-path comparison alone does not prove the open was safely anchored beneath a trusted root.
- File IDs and handle metadata can help compare opened objects, but do not alone prove trusted-root containment or immutable contents. Microsoft documents filesystem-specific file-ID behavior, including reuse over time and changes in some cases. A design still needs a supported root-relative open contract and same-open-handle checks, with constraints for each supported filesystem.

References: Python 3.12 [`os` file and directory APIs](https://docs.python.org/3.12/library/os.html#files-and-directories), [`os.supports_dir_fd`](https://docs.python.org/3.12/library/os.html#os.supports_dir_fd), [`Path.stat()` / `Path.is_junction()`](https://docs.python.org/3.12/library/pathlib.html#querying-file-type-and-status), Microsoft [`OBJECT_ATTRIBUTES`](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes), [`NtCreateFile`](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile), [`CreateFileW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew), [`GetFileInformationByHandleEx`](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getfileinformationbyhandleex), [`BY_HANDLE_FILE_INFORMATION`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/ns-fileapi-by_handle_file_information), and [`GetFinalPathNameByHandleW`](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew).


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

### Concrete Windows test procedure and pass criteria

Run these cases on every OS/filesystem combination admitted by the eventual support matrix. Use a dedicated temporary root and an outside-root sentinel whose bytes and file identity are recorded by the harness. Tests that require symlink/junction privileges must run on a host where those objects can actually be created; an unavailable privilege is a blocked test, not a pass. Do not use mocked path calls as a substitute for these kernel/filesystem cases.

| Case | Deterministic setup | Pass criterion |
| --- | --- | --- |
| Normal in-root files | Place valid JSON and PNG fixtures directly under the root and under a nested ordinary directory; use known sizes, digests, and handle identity observations. | Accept only the intended files; metadata, size, and digest correspond to the object actually opened and read. |
| Outside-root path | Supply `..` traversal, an absolute outside path, and an outside file reached through a drive/UNC form where applicable. | Reject; no candidate is returned and no outside sentinel bytes are consumed as evidence. |
| File/directory symlink and junction | Put a file symlink, directory symlink, and junction at the leaf and at parent components, with targets both inside and outside the trusted root. | Apply the specialist-approved policy consistently. For a no-reparse contract, reject every encountered reparse point, including links whose current target is inside the root. Never accept outside-root content. |
| Reparse traversal | Exercise each supported reparse category/tag in the final and every intermediate component, including mount points and any provider-specific tag in scope. | Reject unsupported or encountered reparse traversal, or prove the exact documented contract for that tag/provider. A final-leaf-only check does not pass. |
| Replacement before open | Add a deterministic synchronization point after root/path validation but before the open; replace the file with a same-size outside-target link and separately replace an intermediate directory with a junction/link. | The operation rejects or reads only the object whose containment and identity are bound by the approved open contract. It must not return a candidate based on the outside sentinel. |
| Replacement during open | Coordinate replacement while the open is in progress using a repeatable test hook/harness; record the identity from the handle that supplies bytes. | The opened/read object is proven to satisfy the trusted-root contract, or the operation fails closed. A pathname recheck after opening is insufficient by itself. |
| Mutation during reads | Pause after the first read; concurrently grow the file past the metadata/PNG limit, then in separate cases truncate it and overwrite bytes with different same-length content. | Read requests and cumulative bytes stay within the configured bound. Accept only if the documented consistency contract is met for the exact bytes hashed; otherwise reject. Length equality alone is not a pass. |
| Permission failures | Deny file read access and, separately, directory traversal/list/open access using a disposable test ACL. | Return controlled rejection, no candidate, and no fallback to a weaker path-based method. |
| Fail-closed/unsupported | Force missing files, unexpected reparse tags, API/query failures, unsupported filesystem behavior, and access-denied errors. | Every unverified condition rejects the artifact and returns no candidate; no exception path marks it valid or enables publication. |

**Execution record for this phase:** source and documentation review only. These Windows acceptance tests were not executed; no pass result is claimed.

## Reviewer decision checklist

- [ ] Supported Windows releases, filesystems, and privilege assumptions are named.
- [ ] Trusted-root establishment and child-open guarantees are supported by authoritative documentation.
- [ ] Intermediate and final reparse behavior is addressed for relevant tags.
- [ ] Identity, type, size, bounded read, and hash apply to the same opened object.
- [ ] Replacement, growth, and same-size mutation guarantees are explicit.
- [ ] Real-platform tests pass for every supported environment, or unsupported cases are rejected.
- [ ] Access-denied and unsupported conditions fail closed.
- [ ] Remaining limitations are documented and accepted by the project owner before implementation review.

## Required written decision outcome

The specialist must select exactly one outcome and state the evidence and scope for it:

- **APPROVED FOR A SEPARATE IMPLEMENTATION PROPOSAL** — the documented contract and acceptance evidence support a proposed implementation for the named OS/filesystem matrix. This does not approve production use or publication.
- **CONDITIONALLY APPROVED** — list each unmet prerequisite, excluded environment, and required evidence. No security-sensitive implementation may begin until the specialist confirms the stated prerequisites are met in writing.
- **REJECTED** — the required containment, object-binding, or consistency guarantees cannot be established for the stated environment; evidence reading remains blocked there.

For any outcome, identify the reviewed API contract and authoritative references, supported Windows/Python/filesystem/privilege matrix, guarantees versus assumptions, acceptance tests and results, limitations, and environments that must be rejected. A successful test call or API availability alone is not approval.

## Decision record

Reviewer: ____________________  Date: ____________________

Supported OS/filesystems: ______________________________________________

Documented API contract and references: __________________________________

Unresolved limitations / rejected environments: __________________________

Decision: [ ] APPROVED FOR A SEPARATE IMPLEMENTATION PROPOSAL  [ ] CONDITIONALLY APPROVED  [ ] REJECTED

This sign-off section is blank. No independent review or approval is claimed. Until completed and accepted, do not change the readers to use a speculative workaround, do not use them as a security boundary for externally supplied artifacts, and do not connect artifact reading to `dom_evidence_package.py` or production collection/publication.

## Phase 66 — independent assessment decision and implementation hold

The independent Windows filesystem security assessment rejected the current evidence-reader design for use as a trusted-root security boundary. This decision applies to the current readers and the evidence available for their review. It does **not** establish that a secure Windows design is impossible.

The original decision form above is retained as review-package history. Its statement that no independent review is claimed describes the package state before this assessment and is superseded by this Phase 66 addendum, which records the subsequent assessment:

- **Decision:** REJECTED FOR THE CURRENT EVIDENCE-READER DESIGN.
- **Evidence reading:** remains blocked; the readers must not be relied on as a trusted-root security boundary.
- **Implementation authorization:** the assessment authorizes no security-sensitive implementation work on the readers.
- **Acceptance evidence:** real-Windows security acceptance tests have not been executed. Existing offline/unit test results do not establish filesystem security.
- **Operational holds:** collection publication remains closed; `AUTO_SUBMIT` must remain false; browser auditing must remain disabled.

### Conditions before reconsidering implementation

Reconsideration requires all of the following to be documented and reviewed:

1. Define the trusted-root path, ownership, ACLs, parent-directory protections, and threat model.
2. Establish the supported Windows, Python, filesystem, storage-provider, and privilege matrix.
3. Resolve the documented API-contract question for safe root-relative opening and reparse traversal.
4. Define how containment and validation bind to the exact opened object.
5. Define guarantees for replacement, truncation, growth, and same-size mutation during reads.
6. Specify fail-closed behavior for unsupported or unverifiable environments.
7. Execute real-Windows acceptance tests for every proposed supported environment and record actual results; a blocked or unavailable test is not a pass.
8. Obtain a new written specialist decision based on the proposed design and actual acceptance-test evidence before authorizing any security-sensitive implementation.

Until a new written decision changes this hold, evidence reading remains blocked and production collection/publication must not consume evidence from these readers.

## Phase 67 — design options for independent review

**Review proposal only.** The Phase 66 rejection remains in force. No option below is selected or approved; this section authorizes no implementation. Evidence reading remains blocked, publication remains closed, and the real-Windows acceptance tests below are **NOT RUN**.

### Evidence categories

- **Confirmed source behavior:** `search_page_evidence.py::_check_screenshot()` resolves and containment-checks paths, stats the target, then separately opens the path, reads in bounded chunks, compares the byte count with the earlier stat size, and verifies a supplied SHA-256 (`search_page_evidence.py:175–247`). `offline_search_evidence.py` similarly resolves/checks paths and separately stats then opens metadata or PNG paths; it applies read limits, PNG signature/hash checks, and size comparisons (`offline_search_evidence.py:51–132, 150–226`). These facts do not prove that the opened object is the validated object, trusted-root containment, or stable contents during a read.
- **Previously observed environment (not rechecked in Phase 67):** the package records Windows 11 build 26200, Python 3.12.14 (64-bit), and the project volume reported as NTFS (`WINDOWS_FILESYSTEM_SECURITY_REVIEW_PACKAGE.md:101–103`). This observation is not an approved support matrix.
- **Owner-provided assumptions:** one personal Windows 11 computer, local storage, owner-created/trusted evidence, and no expected concurrent modification (`:21–35`). They are assumptions, not enforced security facts.
- **Unknowns:** actual root path/owner/ACLs and parent-directory rights; attacker capabilities; exact supported OS/runtime/filesystem/provider/privileges; reparse behavior for an approved open contract; and consistency under concurrent mutation.

### Option A — Windows-native, handle-based design for review

- **Required properties and prerequisites:** establish the trusted root from a protected, retained directory handle; resolve every child component relative to retained handles under a documented, supported Windows contract; bind identity, type, size, and reading to the same opened handle. The specialist must name exact APIs, flags, statuses, OS/filesystem scope, and authoritative contracts. The existing review records a documentation gap between generic `OBJECT_ATTRIBUTES` wording and the `NtCreateFile` page; this proposal does not resolve or approve that approach.
- **Reparse policy:** reject reparse traversal at every component, or provide a specialist-justified, tag-specific policy with containment evidence. Leaf-only checks are insufficient. Account for symlinks, junctions, mount points, and any other tag/provider admitted by the support matrix.
- **Replacement and content consistency:** prove that replacement before/during component opening either cannot redirect the operation outside the retained root or causes rejection. Continue all validation and reads through the returned handles. Define how truncation, growth, and same-size mutation are prevented, detected, or rejected; a handle ID or matching length alone is not a stable-content guarantee.
- **Failure behavior:** missing/denied access, sharing conflict, unsupported API/filesystem/tag, failed metadata query, or any ambiguity must reject the read. No fallback to the current path-based reader.
- **Unresolved / tests:** API contract, matrix, root/ACL model, handle semantics, and mutation behavior remain for specialist determination. Requires the full real-Windows acceptance matrix below on every supported combination. **No prototype or acceptance test is authorized or performed in Phase 67.**

### Option B — restricted supported-environment design for review

- **Required properties and prerequisites:** limit deployment to a named, inspected allow-list of Windows builds, Python versions, filesystems, storage providers, and privileges, with a documented root and enforceable ACL/parent-directory controls. Restrictions narrow where a design may run; they do not themselves provide containment or close a validation/open race. This option still requires the complete documented handle/open and content-consistency contract described for Option A.
- **Reparse and exact-object rules:** explicitly reject unapproved storage and reparse behavior; for every admitted tag/component, prove the approved policy. Validate and read the exact same opened objects; do not rely on path strings or a final-path comparison as the sole proof.
- **Replacement, mutation, and failure behavior:** specify enforceable controls or a documented consistency guarantee for replacement, truncation, growth, and same-size mutation. Reject any host whose configuration, ACL, filesystem/provider, or required query cannot be verified; never fall back to weaker path-based checks.
- **Unresolved / tests:** which restrictions are practical and enforceable, how configuration drift is detected, and whether the underlying contract applies to each allowed environment remain unresolved. Run the full acceptance matrix separately on every allow-listed combination. **All such tests are NOT RUN.**

### Option C — retain the current block

- **Security properties and prerequisites:** make no claim that readers establish containment; do not consume evidence through them as a security boundary. Keep evidence reading blocked and publication closed. No trusted-root, reparse, same-object, or snapshot guarantee is claimed.
- **Replacement, mutation, reparse, and failures:** no reader path is opened for security-sensitive evidence; no acceptance of uncertain inputs. Any future opt-in requires a new written specialist decision and explicitly authorized work.
- **Unresolved / tests:** the security contract remains unresolved. The Windows tests below remain **NOT RUN**; this option preserves the hold and does not assert that a secure implementation is impossible.

### Proposed real-Windows acceptance tests

These cases are designed only. Every status is **NOT RUN**. Tests must use a dedicated disposable root and outside-root sentinel, and must execute on each environment admitted by the eventual support matrix. Missing privilege or unsupported test setup is **BLOCKED**, not passed.

| Case | Setup and pass criterion | Status |
|---|---|---|
| Valid in-root files | Read known JSON/PNG fixtures at root and nested ordinary paths; accept only when containment, handle identity, type, size, and digest apply to the same opened object. | **NOT RUN** |
| Traversal/outside sentinel | Try `..`, absolute, drive/UNC and applicable alternate forms; verify rejection and that sentinel bytes are not consumed. | **NOT RUN** |
| Reparse tags | Exercise file/directory symlinks, junctions, mount points, and each other in-scope tag at leaf and parent components; verify the written policy and no outside read. | **NOT RUN** |
| Intermediate traversal | Put/replace reparse points at each intermediate component; require rejection or evidence for the specialist-approved contract and tag. | **NOT RUN** |
| Replacement before/during opening | Coordinate replacement of file and parent components, including same-size outside-target substitution; require exact contained object or fail-closed rejection. | **NOT RUN** |
| Truncation/growth | Mutate after the first read, including growth beyond each configured bound; verify bounded total reads and documented consistency or rejection. | **NOT RUN** |
| Same-size mutation | Overwrite bytes during a read without changing length; accept only if a documented snapshot guarantee is demonstrated, otherwise reject. | **NOT RUN** |
| Permission/sharing failures | Deny file and directory access and cause sharing conflicts; require controlled rejection and no weaker fallback. | **NOT RUN** |
| Unsupported configuration/query failure | Use an unlisted filesystem/provider/build/tag and force required security-query failures; require explicit rejection/disablement. | **NOT RUN** |
| Fail-closed/no fallback | Exercise every rejected/ambiguous condition; require no candidate accepted, no path-based fallback, and no publication. | **NOT RUN** |

### Questions for the next specialist review

1. What exact root ownership, ACL, parent protection, and attacker model are necessary, and how are they verified/enforced?
2. Which exact supported Windows/Python/filesystem/provider/privilege combinations can meet the contract?
3. What documented user-mode contract supports root-relative opening for each component and prevents or detects all in-scope reparse traversal? Resolve the existing `OBJECT_ATTRIBUTES`/`NtCreateFile` documentation gap without inferring guarantees from export availability or test success alone.
4. How are the root and each opened child tied to the trusted namespace, and how are identity/type/size queried on the same handles that supply bytes?
5. What prevents or detects replacement before/during open, and what content consistency can be guaranteed during concurrent truncation, growth, or same-size mutation?
6. Which errors and environments must be rejected, and how is fallback to the existing path-based sequence prevented?
7. Which tests and results support each admitted matrix entry? Which unavailable tests or environments must remain blocked?
8. What new written decision is made after the design and actual acceptance evidence: approve a separate implementation proposal, conditionally approve with explicit prerequisites, or reject?

No design option or test outcome in this Phase 67 section changes the Phase 66 rejection or authorizes production implementation. A new written specialist decision based on the proposed design and actual test evidence is required before implementation may be reconsidered.

## Phase 68 — consolidated readiness assessment

This section consolidates pre-implementation review inputs. It preserves the Phase 66 rejection and Phase 67 options; it selects no design and authorizes no implementation. Evidence reading remains blocked, publication remains closed, and all security acceptance tests below are **NOT RUN**.

### Environment fact ledger

**Read-only observations in the Phase 68 execution environment:**

- The current directory was `C:\Users\gbhan\Downloads\AI-Job-Automation-updated v1`; that project path exists. The project directory itself reported `Directory` and was not marked as a reparse point. This does not establish anything about its ancestors or identify the trusted artifact root.
- The `C:` drive was ready, reported `Fixed`, and reported `NTFS` through .NET `DriveInfo`. The artifact root was not identified; its volume may differ.
- The project `venv312` Python executable reports Python 3.12.14. The OS and process architecture reported X64.
- The current process identity reported `BHANU\gbhan`; its token was not in the local Administrators role. This does not enumerate all effective file rights or identify which accounts can modify the root.
- Read-only Windows registry values reported `ProductName=Windows 10 Home Single Language`, `EditionID=CoreSingleLanguage`, `DisplayVersion=25H2`, `CurrentBuild=26200`, `UBR=9711`, and `InstallationType=Client`. A `Get-CimInstance Win32_OperatingSystem` query was denied. The prior package records Windows 11 build 26200; the OS label discrepancy is unresolved and must be confirmed by the owner. These observations are not a deployment support policy.
- `AUTO_SUBMIT` was unset in the current process; `config.py` defaults it to false. Source sets `ROUTE_AUDIT_BROWSER_ENABLED = False`, and `job_search.publish_collection()` returns `False` for all outcomes. No workflows were run.

**Owner confirmation required before proposing a support matrix:**

- Exact trusted artifact-root path and whether it is the same as, beneath, or separate from the project directory.
- Root and every parent directory's owner, DACL/ACL, inheritance, and who can create, rename, replace, delete, or change permissions on each component.
- Accounts, services, scheduled tasks, sync/filter software, and same-account processes that can modify those paths or evidence files; whether same-account malicious or compromised processes are in scope.
- Actual Windows product/edition/build and update revision for deployment; Python version, architecture, and runtime distribution.
- Filesystem and storage provider for the artifact root: local, network/SMB, removable, synchronized, virtual, or filter-mediated; effective privileges and whether symlink/junction creation is possible.
- Reparse points present or possible in the root, its ancestors, and every descendant component; whether concurrent writers or replacement are possible and which attacker capabilities must be resisted.
- Whether 256 KiB metadata and 10 MiB screenshot limits meet the application requirements.

The repository's current documentation records owner assumptions of a personal Windows 11 machine, local storage, owner-created evidence, and no expected concurrent modification. These remain assumptions, not verified or enforced facts. The trusted root, its ACLs, parent controls, actual deployment matrix, and concurrent-writer capabilities remain unknown.

### Consolidated design comparison

The Phase 67 option descriptions remain the detailed proposal. This table summarizes their present status without approving a design:

| Option | What it would require / trade-off | Present assessment |
|---|---|---|
| A. Windows-native handle-based design | A documented, supported trusted-root and component-opening contract; explicit reparse policy; same-handle validation and reads; a defined content-consistency model. The exact user-mode root-relative/reparse contract remains unresolved. | Review only; no API contract, support matrix, or acceptance evidence establishes security. Not authorized. |
| B. Restricted supported environments | An inspected, enforceable allow-list and protected root, **plus** the full opening and content-consistency contract of A. Narrowing environments does not itself prevent path races. | Review only; no allow-list or proof that restrictions provide the required guarantees. Not authorized. |
| C. Maintain current security hold | Do not use these readers as a security boundary; keep evidence reading blocked and publication closed. | Current required operational posture. It is not a secure-reader design and does not imply safe implementation is impossible. |

### Consolidated real-Windows acceptance matrix

Every test below is **NOT RUN**. The support-matrix column applies separately to each future candidate configuration; currently **no configuration is approved**. Run only in a dedicated disposable environment after the specialist defines the contract and the test work is separately authorized. An unavailable privilege or test setup is **BLOCKED**, not PASSED.

| Test / security property | Required setup | Observable pass criterion | Evidence to retain | Applies to | Status |
|---|---|---|---|---|---|
| Valid in-root files; root-relative containment | Known JSON/PNG fixtures at root and nested ordinary directories; baseline size, digest, and object identity. | Accept only when the root relation and type, identity, size, and bytes are established for the same opened object. | Configuration record; root/ACL summary; handle/object metadata; bytes read, sizes, expected/actual digests, and result. | Each separately proposed OS/build, Python/runtime, filesystem/provider, and privilege cell. None approved. | **NOT RUN** |
| Outside-root sentinel; path traversal | Sentinel outside root; try relative `..`, absolute, drive, UNC, and applicable alternate path forms. | Reject and show no sentinel bytes were consumed or accepted. | Input path form; sentinel identity/hash; reader outcome and read trace. | Each proposed support cell. None approved. | **NOT RUN** |
| Leaf symlinks, junctions, mount points, other tags | Create each in-scope leaf tag with in-root and outside-root targets. | Follow the written policy; under reject-reparse policy, reject every encountered tag; never accept outside bytes. | Tag and target description; privilege/setup result; handle/tag query; sentinel and reader outcome. | Each proposed support cell and tag. None approved. | **NOT RUN** |
| Intermediate reparse traversal | Place and replace each in-scope reparse tag at every intermediate component and root boundary. | Reject traversal or demonstrate the specialist-approved contract for that tag and component; no outside read. | Component sequence; tag and target; timing; handle identities; sentinel result. | Each proposed support cell and tag. None approved. | **NOT RUN** |
| File/parent replacement before open | Synchronize a replacement after path/root validation and before child open; substitute same-size outside-target file and parent junction/link. | Open only the proven contained object or fail closed. | Synchronization trace; before/after identities; sentinel hash; outcome. | Each proposed support cell. None approved. | **NOT RUN** |
| Replacement during opening | Repeatable race harness replaces target and parent while opening is in progress. | The opened handle is proven to satisfy the contract or operation rejects; no path recheck-only result. | Harness timing; open status; identities from relevant handles; sentinel result. | Each proposed support cell. None approved. | **NOT RUN** |
| Truncation and growth | Mutate after first read; grow beyond each configured bound and truncate in separate runs. | Bounded reads stay within limits; accept only under the documented consistency contract, otherwise reject. | Initial/final metadata; per-read lengths; cumulative bytes; mutation timing; digest and result. | Each proposed support cell. None approved. | **NOT RUN** |
| Same-size mutation | Overwrite bytes after partial read without changing file length. | Accept only if a documented snapshot/consistency guarantee holds for the exact bytes hashed; otherwise reject. | Mutation timing; per-read bytes/hash; handle metadata/identity; result. | Each proposed support cell. None approved. | **NOT RUN** |
| Permissions and sharing failures | Deny file access and directory traversal/open access; trigger sharing violations with disposable test ACLs/handles. | Controlled rejection, no candidate, and no weaker fallback. | ACL/test setup; requested operation; error/status; reader result. | Each proposed support cell. None approved. | **NOT RUN** |
| Unsupported configuration or failed security query | Exercise unlisted build/filesystem/provider/tag/privilege and force required identity/type/reparse queries to fail. | Explicitly disable/reject evidence reading; no path-based fallback. | Configuration identity; failed query/status; decision and outcome. | Every unsupported or failed-query case for the proposed matrix. None approved. | **NOT RUN** |
| Fail-closed/no fallback | Inject each malformed, ambiguous, permission, query, race, and unsupported condition. | No candidate is accepted, no weaker reader is used, and publication remains closed. | Trigger, trace, exception/status mapping, candidate result, publication gate result. | Each proposed support cell and each rejected condition. None approved. | **NOT RUN** |

Record exact OS product/edition/build/revision, Python version/distribution/architecture, filesystem/provider, privileges, root path and ACL summary for each run. Preserve reproducible harness version, setup, synchronization logs, handle/object metadata, sentinel identity/hash, actual outputs and exit status, and whether the test was PASSED, FAILED, BLOCKED, or NOT RUN. Do not report a blocked case as a pass.

### Consolidated specialist decision request

Before implementation is reconsidered, the specialist must answer in writing:

1. What root path, ownership/ACL/parent protections, and attacker model are required, including same-account processes?
2. Which exact Windows builds/editions, Python versions/architectures, filesystems/providers, and privilege profiles can be supported, and which must be rejected?
3. What authoritative, supported user-mode contract permits opening each component relative to the trusted root and defines behavior for all in-scope reparse tags? Resolve the `OBJECT_ATTRIBUTES`/`NtCreateFile` documentation uncertainty for the exact call and support matrix; do not rely on symbol availability or a successful call as proof.
4. How is the root handle itself trusted, and how are descendant containment and validation bound to the same opened objects used for reads? Which identity/type/size/reparse metadata is queried on those handles, and what are its filesystem limitations?
5. What guarantees apply to replacement before/during open? What mechanism provides the required byte-consistency behavior under truncation, growth, or same-size mutation, and what remains impossible or unsupported?
6. What conditions must fail closed, and how is fallback to the current path-based sequence prevented?
7. Which matrix entries have completed acceptance tests, which failed, and which remain blocked or unrun? What are the explicit pass criteria for every supported entry?
8. What is the decision—approved for a separate implementation proposal, conditionally approved with explicit prerequisites, or rejected—and what exact work, if any, does it authorize? Production use/publication require separate approval.

Any future approval must include the signed threat/root/ACL model; exact support matrix; authoritative API references and documented-versus-assumed guarantee table; design and failure semantics; complete per-configuration test reports and retained evidence above; explicit exclusions/limitations; and the specialist's signed decision. Until then, the Phase 66 rejection and implementation hold remain binding.

## Phase 69 — owner validation and handoff readiness

This addendum preserves the Phase 66 rejection, Phase 67 options, and Phase 68 environment ledger and acceptance matrix. It supplements that single handoff with owner-confirmation status and size-limit context; it does not select a design, authorize implementation or testing, or change the current hold. Evidence reading remains blocked, collection publication remains closed, `AUTO_SUBMIT` remains disabled, browser auditing remains disabled, and no security acceptance tests were run.

### Owner-confirmation register

Status labels distinguish observed facts from information that only the owner can establish. “Confirmed” below means confirmed only for the current inspection process/environment, not an approved deployment guarantee.

| Item | Status | Evidence / required owner input |
|---|---|---|
| Exact trusted artifact-root path | **UNKNOWN** | No fixed root is configured in the inspected reader APIs. `offline_search_evidence.prepare_candidate()` accepts `artifact_root`; `search_page_evidence.validate_evidence_fixture()` also accepts it as an argument. No caller or owner-identified production artifact root was established. Do not substitute the project directory. |
| Root and ancestor ownership | **OWNER CONFIRMATION REQUIRED** | The artifact root has not been identified, so its owner and every ancestor's owner are unknown. Supply the exact path and ownership for each component. |
| ACLs and inherited permissions | **OWNER CONFIRMATION REQUIRED** | No ACL inspection was performed because no trusted root was identified. Provide effective DACLs, inheritance, and principals able to create, rename, replace, delete, or change permissions on every path component. |
| Accounts/processes able to modify root or ancestors | **OWNER CONFIRMATION REQUIRED** | Identify user accounts, services, scheduled tasks, sync/filter software, administrators, and same-account processes that can modify the root, ancestors, or evidence files. |
| Same-account malicious or concurrent process threat | **OWNER CONFIRMATION REQUIRED** | The prior “no expected concurrent modification” statement is an assumption, not an exclusion or enforced control. State whether malicious/compromised processes under the same account and benign concurrent writers are in scope. |
| Windows product, edition, build, architecture | **OWNER CONFIRMATION REQUIRED** | Current read-only observations: `cmd.exe /c ver` reported `10.0.26200.9711`; .NET reported version `10.0.26200.0`; the registry reported `Windows 10 Home Single Language`, `CoreSingleLanguage`, `25H2`, build `26200`, UBR `9711`, Client. `Win32_OperatingSystem` and `Get-ComputerInfo` failed with a CIM access-denied-to-client error; `DISM /online /Get-CurrentEdition` returned error 740 (elevation required). These observations do not conclusively resolve the product-name conflict with the earlier package's Windows 11 description. Confirm the installed product/edition from an owner-accessible OS-reported source; do not infer it from build number. X64 architecture was observed. |
| Python version and architecture | **CONFIRMED** | Project `venv312` reports Python 3.12.14; runtime and process architecture are AMD64/X64, 64-bit. Confirm separately if deployment will use another interpreter or architecture. |
| Filesystem/storage provider at actual artifact root | **UNKNOWN** | Phase 68 observed the `C:` volume as fixed NTFS, but the artifact root is unidentified and may be on a different volume or provider. Owner must identify local/network/SMB/removable/synchronized/virtual/filter-mediated storage for the actual root. |
| Effective privileges | **UNKNOWN** | Current process identity was `BHANU\gbhan` and was not in the local Administrators role. This does not establish effective access to an unidentified root, enabled privileges, ACL-derived rights, or deployment identity. |
| Reparse-point conditions | **UNKNOWN** | The project directory was previously observed not to have the reparse-point attribute; that does not establish the state of the artifact root, ancestors, descendants, or concurrent substitutions. Identify permitted/present reparse tags and whether their creation is possible. |
| Concurrent writers/replacement possibility | **OWNER CONFIRMATION REQUIRED** | No enforceable exclusion was established. Identify writers and whether replacement, truncation, growth, rename, or in-place writes can occur during validation/open/read. |
| Evidence size limits in source | **CONFIRMED** | `search_page_evidence.py` uses `MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024`; `offline_search_evidence.py` uses `MAX_METADATA_BYTES = 256 * 1024` and `MAX_PNG_BYTES = 10 * 1024 * 1024`. See the limit assessment below. |
| Application size requirements / whether smaller limits are acceptable | **OWNER CONFIRMATION REQUIRED** | Source and tests show caps, not the observed size distribution or the largest legitimate metadata/screenshots. Owner must confirm expected evidence formats and maximum legitimate sizes before changing or narrowing a cap. |

### Evidence-size limit assessment

- **Metadata:** the offline reader caps metadata JSON at 256 KiB, checks a pre-open `stat()` size, then reads at most `MAX_METADATA_BYTES + 1` and rejects an over-limit read (`offline_search_evidence.py:24, 65–83`). Its application purpose is parsing the supplied offline evidence metadata as a UTF-8 JSON object. The source does not provide production size distributions or a maximum legitimate metadata size. A smaller cap could reject legitimate evidence; whether it would is **UNKNOWN** pending owner data.
- **PNG evidence:** both readers cap screenshots at 10 MiB. The offline PNG reader checks the pre-open size, reads the signature and bounded chunks up to the cap plus one byte, hashes bytes read, and compares total bytes with the earlier size (`offline_search_evidence.py:24–27, 103–132`). The search-page validator reads bounded chunks and hashes the screenshot, then compares total bytes to the earlier `stat()` size (`search_page_evidence.py:77, 175–247`). The application purpose is to constrain and hash screenshot evidence. A smaller cap could reject larger legitimate screenshots; prevalence is not established by source/tests.
- These caps are resource and input-size checks. They do **not** establish trusted-root containment, bind a later path-based open to a prior path check, identify the opened object as the validated object, or guarantee a stable snapshot under same-size mutation. Changing a cap would not resolve the filesystem security blocker. No limit was changed.

### Reconsideration prerequisites and dependency sequence

The eight Phase 66 prerequisites remain the gate. Their present dependencies are:

| Phase 66 prerequisite | Current status / dependency |
|---|---|
| 1. Define root path, ownership, ACLs, parent protection, and threat model | Root and ACL facts require owner confirmation and environment inspection. Same-account and concurrent-process threat scope requires an owner decision. |
| 2. Establish Windows/Python/filesystem/provider/privilege matrix | Python and process architecture were observed locally; Windows product identity has an unresolved discrepancy; artifact-root filesystem/provider and effective rights require owner/environment confirmation. No support cell is approved. |
| 3. Resolve supported root-relative opening and reparse-traversal API contract | Requires specialist clarification with authoritative documentation for the exact calls, flags, statuses, and every supported configuration. API availability or a successful call is insufficient. |
| 4. Bind containment/validation to the exact opened object | Requires a specialist-defined contract covering root handle trust, each path component, handle identity/type/size/reparse metadata, and bytes read. Not established. |
| 5. Define replacement/truncation/growth/same-size mutation guarantees | Requires owner threat scope and specialist definition of achievable consistency guarantees and limitations. Not established. |
| 6. Specify fail-closed behavior for unsupported/unverifiable environments | Requirements are stated in this package and policy; an implementation and its fallback behavior are not verified. Specialist must confirm rejected conditions and no-fallback semantics. |
| 7. Execute real-Windows acceptance tests for every proposed supported environment | Requires a specialist-approved contract and named support matrix, a disposable Windows test environment, and separate authorization to execute those tests. The Phase 68 matrix remains **NOT RUN**. |
| 8. Obtain a new written specialist decision based on design and actual evidence | Depends on prerequisites 1–7 and retained test evidence. Phase 66 rejection remains binding until then. |

Recommended single-pass sequence: (1) owner supplies the root, ACL/ownership, writer/threat, deployment, provider, privilege, and size-requirement facts in the register; (2) specialist reviews the completed register and existing Phase 67 options/Phase 68 matrix and returns the exact documented contract, support matrix, exclusions, and pass criteria; (3) owner separately authorizes only the real-Windows acceptance work, which records each configuration and each result as PASSED, FAILED, BLOCKED, or NOT RUN with retained evidence; (4) specialist issues a new written decision against that evidence, explicitly stating whether a separate implementation proposal is authorized and its prerequisites; (5) any implementation work remains prohibited until that written authorization exists. Production use, evidence reading, and publication require their own applicable approval gates. This sequence is a proposed workflow, not security approval.

### Safe progress, dependencies, and hold

- **A — Safe work possible now:** preserve the current package and Phase 66 hold; collect owner answers and deployment facts; resolve the Windows product identity through an owner-accessible OS-reported source; obtain representative legitimate evidence sizes without opening them through the blocked readers. No tests or workflows were run in this phase.
- **B — Owner confirmation required:** complete the root/ancestor, ACL, writer/threat, deployment, storage/provider, privilege, reparse, concurrency, and application-size entries above.
- **C — Specialist clarification required:** resolve the exact documented supported API contract, path-component/reparse semantics, same-object binding, content-consistency guarantees, unsupported configurations, and fail-closed/no-fallback behavior; identify which support cells and tags will be tested.
- **D — Real-Windows acceptance required:** after the contract and support matrix exist and test execution is separately authorized, execute every applicable case in the existing Phase 68 matrix on every proposed supported configuration. No case is currently passed.
- **E — Forbidden until explicit written authorization:** security-sensitive reader implementation, any weakening of the current hold, enabling evidence reading or collection publication, or production workflow changes. No alternative design is approved.

### Phase 69 execution record

- Project directory was confirmed to exist. A single `git status --short --branch` attempt returned exit code 128 and `fatal: this operation must be run in a work tree`; repository status and change inventory therefore remain unknown. Git diagnostics stopped after that failure.
- No production code, tests, protected CSVs, screenshot, configuration, or safety controls were modified. No tests, browsers/CDP, live sites, collection, or application workflows were run. Only this review package received a documentation-only addition.
- The security hold remains unchanged: evidence reading is blocked; publication is closed; `AUTO_SUBMIT` defaults to false and browser auditing remains disabled.

## Phase 70 — final pre-implementation decision package

This section closes the remaining owner and specialist decisions without repeating the Phase 66–69 analysis. The Phase 66 rejection remains binding. No option is approved, no implementation is authorized, and evidence reading/publication remain blocked. The Phase 68 acceptance matrix is reused; its current readiness is classified below.

### Actionable owner decision register

Gate labels: **A** owner-confirmed environment and threat model; **B** written specialist decision on design and support matrix; **C** separate authorization to execute Windows acceptance tests; **D** actual acceptance results for every proposed supported configuration; **E** new written specialist decision explicitly authorizing or rejecting implementation. “Blocks” gives the earliest gate that cannot be passed without the item; it is not authorization to proceed.

| Owner decision | Current value | Evidence source | Confidence / limitation | Owner decision required | Why it matters | Blocks |
|---|---|---|---|---|---|---|
| Exact trusted artifact-root path and callers | **UNKNOWN.** No fixed production root is configured. Both APIs receive a caller-supplied `artifact_root`. `offline_search_evidence.prepare_evidence_candidate(metadata_path, *, artifact_root, screenshot_path=None)` uses it for metadata JSON and optional PNG; its call to `validate_evidence_fixture(candidate, artifact_root=None)` does not open another artifact. `search_page_evidence.validate_evidence_fixture(fixture, *, artifact_root=None)` uses the supplied root to resolve/hash `screenshot.reference`. The inspected source search found no production call sites passing a root; explicit callers are test helpers/fixtures. | `offline_search_evidence.py:150–165, 178–180, 190–218`; `search_page_evidence.py:175–224, 250`; `tests/test_offline_search_evidence.py:72–96`; `tests/test_search_page_evidence.py:90–95`; `config.py` has no artifact-root setting; repository-wide source search. | High confidence for the inspected source/configuration snapshot. Git status failed, so the repository change inventory is unknown; absence in the inspected tree does not prove what an external runtime or uninspected deployment supplies. | Name the exact production evidence root, identify the runtime component/caller that supplies it, and state its relation to the project directory. Do not use the project path by default. | Defines the namespace and ancestors for the containment claim; without it there is no actual production root or support environment to assess. | A (then B–E) |
| Root and ancestor ownership, ACLs, inheritance | **UNKNOWN; not inspected.** | No artifact root was identified, so no root/ancestor ACL query was made. | Cannot infer from the project directory, current user identity, or C: volume. | Supply the exact path and per-component owner, effective DACL/inheritance, and principals able to create, rename, replace, delete, or change security. | Determines whether the namespace can be redirected or altered by in-scope principals. | A (then B–E) |
| Accounts/processes able to modify root or ancestors | **UNKNOWN.** | No root/ancestor security descriptors or process/service inventory were inspected. | Owner/deployment fact; not inferable from source. | Identify users, administrators, services, scheduled tasks, synchronization/filter software, and processes with write/rename/delete/security-control rights over every component and evidence file. | Establishes who can replace/mutate the namespace and whether proposed protections are enforceable. | A (then B–E) |
| Same-account malicious/concurrent process threat | **UNKNOWN.** Earlier “no expected concurrent modification” is an owner assumption. | Phase 67 owner-assumption record; no enforceable exclusion or source control found. | Assumption only; not a guarantee. | Explicitly state whether malicious/compromised same-account processes and benign same-account concurrent writers are in scope; justify any exclusion. | A same-account process may be able to alter files even when no writer is expected. | A (then B–E) |
| Windows product and edition | **UNRESOLVED.** `ver`: `10.0.26200.9711`; registry: Windows 10 Home Single Language / CoreSingleLanguage / 25H2 / build 26200 / UBR 9711 / Client. OS architecture observed 64-bit. | `cmd.exe /c ver`; `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion`; `[Environment]::Is64BitOperatingSystem`; prior CIM/Get-ComputerInfo attempts denied; Phase 69 DISM query required elevation. | Product label conflicts with prior Windows 11 description. No elevated commands or registry changes; do not infer product from build. | Confirm actual installed Windows product/edition and revision through an owner-accessible OS-reported source; state deployment support target. | API and filesystem claims/tests must be tied to actual supported OS configurations. | A (then B–E) |
| Python version and architecture | **CONFIRMED locally:** project venv Python 3.12.14, AMD64, 64-bit. | `venv312\Scripts\python.exe`; Python `platform`/pointer-size output; executable path in project. | Applies to this venv/process only; deployed runtime still needs confirmation if different. | Confirm whether production uses this exact interpreter distribution/version/architecture. | The contract and test results must apply to the deployed runtime. | A (then B–E) |
| Filesystem/storage provider at actual artifact root | **UNKNOWN.** Phase 68 and this inspection observed C: as fixed NTFS; actual root is unknown and may be elsewhere. | Read-only `.NET DriveInfo` query for C:; actual root is not configured in source. | C: observation is not evidence about the artifact root or its provider. | Name the root and identify its filesystem/provider (local, SMB/network, removable, synchronized, virtual, filter-mediated, etc.); list accepted and rejected providers. | Filesystem/provider semantics may affect handles, identity, reparse traversal, and mutation. | A (then B–E) |
| Effective privileges | Current process `BHANU\gbhan`; not in local Administrators role. `whoami /priv` showed `SeChangeNotifyPrivilege` enabled and `SeIncreaseWorkingSetPrivilege` disabled. | `[WindowsIdentity]::GetCurrent()`, non-elevated `WindowsPrincipal.IsInRole()`, and `whoami /priv`. | Observed token only; does not establish effective access or privileges for an unidentified root or another deployment process. | Provide deployment identity/token and effective rights on the identified root/ancestors, without treating non-admin status as proof of least privilege. | The open/query contract and pass criteria depend on the actual access profile. | A (then B–E) |
| Reparse-point conditions and policy | **UNKNOWN for the artifact root.** | Root not identified; no root/ancestor/descendant inspection performed. Phase 68 only noted the project directory itself was not marked as a reparse point. | Project-directory attributes do not describe artifact-root ancestors, descendants, or concurrent replacements. | Identify existing/possible tags and decide which are rejected or supported at root, ancestors, intermediate components, and leaf; include symlinks, junctions, mount points, and other tags. | Every path component must be governed by the specialist-approved contract. | A (then B–E) |
| Concurrent writers and replacement | **UNKNOWN; no enforceable exclusion established.** | No identified root/writer inventory or runtime guarantee. | Prior “no expected modification” is not an enforced constraint. | Identify writers and state whether rename/replacement, truncation, growth, or in-place writes may overlap validation/open/read; document any enforceable exclusion. | Determines required same-object and content-consistency guarantees and race tests. | A, B, D, E |
| Required content-consistency guarantee | **UNKNOWN.** Source detects some size changes but does not establish a stable snapshot under same-size mutation. | `offline_search_evidence.py:65–79, 103–128`; `search_page_evidence.py:214–247`; Phase 25 limitations. | A length check/hash of bytes read does not itself define the application’s required snapshot/consistency semantics. | State what consistency the application requires and what outcomes are acceptable under concurrent mutation; specialist must define achievable guarantees/limitations. | Gives the reviewer a testable acceptance condition for replacement, truncation, growth, and same-size mutation. | A, B, D, E |
| Metadata and PNG size limits | Metadata JSON **256 KiB**; PNG **10 MiB** in both readers. Metadata pre-stats then reads at most cap+1; PNG readers pre-stat and bounded-read/hash, with size comparison. | `offline_search_evidence.py:24–25, 65–83, 103–132`; `search_page_evidence.py:77, 214–247`. | Limits and enforcement are verified in source. No production-size distribution or legitimate maximum was examined; suitability remains unknown. These caps do not establish containment or immutable contents. | Confirm expected formats and legitimate maximum/representative sizes using owner requirements or a non-reader-based inventory; state whether current caps meet requirements. | A smaller cap could reject legitimate artifacts; changing a cap does not fix the filesystem security blocker. | A (then B–E) |

**Phase 71 inspection note:** `config.py` contains no artifact-root setting. The only discovered call sites that supply explicit roots are tests; the production root cannot be established from the inspected source/configuration. The owner must identify the actual root and its supplying runtime/caller. No ACL inspection was substituted on the project directory. One `git status --short --branch` attempt failed with exit code 128, `fatal: this operation must be run in a work tree`; repository state remains unknown and Git diagnostics stopped.

### Written specialist decision request

After Gate A, request one written response that:

1. Names supported and rejected Windows products/editions/builds, Python distributions/versions/architectures, filesystems, storage providers, and privilege configurations.
2. Defines the trusted root, required root/ancestor ownership and ACL protections, and the in-scope attacker/process model.
3. Identifies the exact documented supported API contract for root-relative component opening and handling of intermediate and leaf symlinks, junctions, mount points, and other in-scope reparse tags. It must resolve the existing `OBJECT_ATTRIBUTES`/`NtCreateFile` contract uncertainty for the exact calls and supported configurations.
4. Explains how root trust and containment are established for every opened component, and how type, identity, size, and the exact bytes read are bound to the same opened object(s), including filesystem limitations.
5. States guarantees and limitations for replacement before/during opening, truncation, growth, and same-size mutation.
6. Defines mandatory fail-closed conditions and prohibits fallback to the existing path-based reader or any weaker check if required guarantees or queries are unavailable.
7. Specifies the existing Phase 68 acceptance tests, pass criteria, and retained evidence for every supported configuration, including rejection of unsupported configurations.
8. States the decision and exact authorization scope: **approved**, **conditionally approved with explicit prerequisites**, or **rejected** for a separate implementation proposal; production use and publication require separate approval.

Silence, partial answers, API availability, a successful sample call, and unexecuted tests are not approval and do not lift the Phase 66 hold. The specialist must distinguish documented guarantees, assumptions, limitations, and unresolved questions.

### Separate dependency gates

| Gate | Required completion evidence | Does not automatically authorize |
|---|---|---|
| **A — Owner-confirmed environment/threat model** | Completed register with root/ACL/writer/deployment/provider/privilege/size evidence and explicit threat scope. | Specialist approval, test execution, or implementation. |
| **B — Written specialist design decision** | Exact documented contract, support matrix, limitations, fail-closed rules, acceptance criteria, and explicit decision. | Test execution or implementation. |
| **C — Separate test authorization** | Owner explicitly authorizes the defined Windows test plan in a disposable environment after B identifies configurations and criteria. | Passing results or implementation. |
| **D — Actual acceptance results** | Retained environment identity, setup, traces/object metadata, sentinel outcomes, outputs, and result for every required test/configuration. Failed and blocked results remain visible. | Implementation until specialist review of the actual evidence. |
| **E — New written implementation decision** | Specialist decision based on A–D that explicitly authorizes or rejects a bounded implementation proposal, with prerequisites/exclusions. | Production evidence reading, publication, or application behavior; these remain separately gated. |

Passing one gate does not pass the next.

### Existing acceptance-matrix readiness

The test procedures and criteria remain in the Phase 68 matrix; no second test plan is created here. Every case is currently **BLOCKED — NOT RUN** because no contract/support matrix is approved and there is no separate test authorization:

| Existing Phase 68 case | Current status |
|---|---|
| Valid in-root files and root-relative containment | **BLOCKED — NOT RUN** |
| Outside-root sentinel and path traversal | **BLOCKED — NOT RUN** |
| Leaf symlinks, junctions, mount points, and other tags | **BLOCKED — NOT RUN** |
| Intermediate reparse traversal | **BLOCKED — NOT RUN** |
| File/parent replacement before opening | **BLOCKED — NOT RUN** |
| Replacement during opening | **BLOCKED — NOT RUN** |
| Truncation and growth | **BLOCKED — NOT RUN** |
| Same-size mutation | **BLOCKED — NOT RUN** |
| Permission and sharing failures | **BLOCKED — NOT RUN** |
| Unsupported configuration or failed security query | **BLOCKED — NOT RUN** |
| Fail-closed behavior/no fallback | **BLOCKED — NOT RUN** |

No case is READY FOR AUTHORIZED EXECUTION until Gates A and B are complete and the owner separately passes Gate C. No test was run in Phase 70.

### Next decision and hold

The next specific decision required is Gate A: the owner supplies the unknown artifact-root, ACL/ownership, modifying-principal, threat-scope, deployment, provider/privilege/reparse, concurrency, and evidence-size facts in the register. The completed existing package can then be submitted once for Gate B. Until Gates A–E are passed in order, evidence reading remains blocked, collection publication remains closed, `AUTO_SUBMIT` remains false, browser auditing remains disabled, and security-sensitive implementation remains unauthorized.

## Phase 72 — static caller and runtime-architecture audit

Source-only review of the currently inspected project tree. No application, reader, test, browser, or collection workflow was executed. This adds the caller/data-flow result to the existing owner register; it does not identify a production artifact root or alter the Phase 66 rejection.

### Call graph

```text
Offline evidence tests (confirmed source calls)
tests/test_offline_search_evidence.py:72–96
  setUp() -> TemporaryDirectory(dir=project_root) -> self.root [test fixture only]
  prepare() -> prepare_evidence_candidate(..., artifact_root=self.root)
    offline_search_evidence.py:150–224
      resolve/check root and metadata -> _read_metadata(path)
      if an explicit screenshot_path is supplied:
        _resolve_under_root -> _relative_reference -> _hash_png(path)
      -> validate_evidence_fixture(candidate, artifact_root=None) [schema check;
         screenshot field was removed, so this call opens no artifact]

Search-page evidence tests (confirmed source calls)
tests/test_search_page_evidence.py:90–95, 131–399
  helper/direct test calls -> validate_evidence_fixture(fixture, artifact_root=...)
    search_page_evidence.py:250–573
      -> _check_screenshot(...) at :175–247
         -> resolve/stat/open/hash the supplied screenshot reference

In-repository collection path (confirmed source calls; no reader edge found)
job_search.py __main__ :2018–2020 -> search_jobs() :2003–2011
  -> _collect_search_jobs() :1035–2000
     -> _collection_outcome() :301–334
        -> adapt_collection_outcome() :322
        -> classify_collection_run() :323
     -> publish_collection() :1952 -> publish_collection() :376–395 [returns False]
  Imports: collection_diagnostics_adapter :9–17 and collection_run_evidence :10–15.
  Neither imports or calls either filesystem evidence reader.

Other inspected module edges
collection_diagnostics_adapter.py :9–17 -> collection_run_evidence only
dom_evidence_package.py :15–25 -> collection_run_evidence only;
  validate_dom_evidence_package() :558–579 validates an in-memory mapping
  and does not open the artifact references
execution_policy.py :3 -> config only
job_scraper.py __main__ :561–563 -> scrape_jobs() [separate path]
dashboard.py __main__ :252–253 -> main() -> load_jobs()/show_dashboard()
  [CSV/dashboard path; no reader import found]
main.py [no reader import or reader call found]
```

The source search found no alias, wrapper, callback, CLI, scheduler, dashboard, or application call path to `prepare_evidence_candidate()` or `validate_evidence_fixture()` outside the tests and the reader-to-reader schema-validation call described above. No dynamic import of either reader was found; unrelated `__import__("re")` uses do not reference them. Static search cannot rule out an external host importing these callable APIs, reflection/monkey-patching, generated code, or files outside the inspected project tree. Therefore the accurate conclusion is: **test-only call sites in the inspected repository source; production/runtime reachability remains unresolved, not proven impossible.**

### Root and file data flow

| Path | Root origin and forwarding | Possible file access and failure behavior | Execution-path conclusion |
|---|---|---|---|
| `prepare_evidence_candidate()` | Required keyword argument from its caller; no config/environment binding. `Path(artifact_root).resolve(strict=True)` and `is_dir()` precede resolution of `metadata_path`. A relative input is joined to root; an absolute input is used as supplied, then strict resolution/containment/file checks are applied (`offline_search_evidence.py:51–62, 150–170`). | Opens only the explicitly supplied `.json` metadata path. If `screenshot_path` is supplied, resolves that `.png`; if metadata declares a screenshot but none is explicitly supplied, returns a failed preparation. Metadata/root/path failures return no candidate with UNKNOWN status; screenshot errors also fail preparation (`:172–224`). It does not scan directories or write files. | Only test callers supply roots in the inspected tree (`tests/test_offline_search_evidence.py:91–96`). No production root/caller is configured or established. |
| `validate_evidence_fixture()` | Optional keyword argument from caller; no config/environment binding. For a present screenshot, requires a relative reference and a non-`None` root; resolves root and target and checks containment (`search_page_evidence.py:188–213, 250`). | May open only the referenced screenshot to check regular-file type, 10 MiB bound, bytes/hash, and supplied digest (`:214–247`). With screenshot absent it performs no screenshot read; with root absent and screenshot present, it records a validation issue and returns without opening the file. I/O/resolve failures become issues. | Called directly by tests and internally by `offline_search_evidence` with `artifact_root=None` after stripping the screenshot field; no production caller found. |
| Collection/package path | No `artifact_root` parameter or setting found in `job_search.py`, `collection_run_evidence.py`, `collection_diagnostics_adapter.py`, `dom_evidence_package.py`, `execution_policy.py`, or `config.py`. | `dom_evidence_package` validates artifact-reference strings and package structure in memory; it does not open those files. Collection diagnostics do not acquire page artifacts. `publish_collection()` always returns `False`. | No static in-repository edge from collection, classification, package validation, dashboard, or publication to either reader. External embedding remains unverified. |

### Architectural boundary and owner decision

The source establishes a separation in the current in-repository call graph: live `job_search` diagnostics flow through the in-memory adapter/classifier and a publisher that remains closed; the offline readers are referenced by their tests, not by that collection path. `COLLECTION_EVIDENCE_POLICY.md:87–118, 173–234` independently states that production collection does not acquire verified page evidence, the adapter is in-memory only, the readers are a separate blocker, and publication remains fail-closed. Existing static tests assert import isolation for the offline reader, collection model, adapter, and DOM package, but those assertions were inspected, not executed in this phase.

This is not proof of runtime unreachability: the public Python functions can be called by an external launcher, embedding service, or code outside the scanned tree. The owner must answer: **Which exact production component, if any, is intended to call either reader; what is its full entrypoint/call chain; which component supplies each root/path argument; and is that runtime part of this deployment?** If the intended answer is “none,” record that the readers are offline/test utilities and identify any external integration that must be excluded. Until answered, production/runtime reachability remains unresolved and Gate A remains incomplete.

No artifact-root ACL was inspected because no actual root was identified. The Phase 69 OS-product discrepancy and all owner threat/deployment questions remain open. The Phase 66 rejection, blocked evidence reading, closed collection publication, and implementation hold remain unchanged.

## Phase 73 — reader intent and next-milestone decision

This section records the owner-intent question left open by the Phase 72 static call-graph review. It does not change the Phase 66 rejection, identify a production artifact root, approve a reader design, or establish runtime unreachability. Static source inspection only; no tests or workflows were run.

### Component map and trust boundaries

```text
Production collection (source path)
job_search.py __main__ :2018–2020 -> search_jobs() :2003–2011
  -> _collect_search_jobs() :1035–2000
  -> _collection_outcome() :301–334
  -> collection_diagnostics_adapter.adapt_collection_outcome()
  -> collection_run_evidence.classify_collection_run()
  -> publish_collection() :376–395 / call at :1952 [always returns False]

In-memory evidence paths
collection_diagnostics_adapter.py :9–17 -> collection_run_evidence.py
dom_evidence_package.py :558–579 validates an in-memory package mapping;
  it does not open referenced files and does not establish filesystem trust.

Filesystem evidence helpers (confirmed in-repository call sites are tests)
tests/test_offline_search_evidence.py -> offline_search_evidence.py
  prepare_evidence_candidate(..., caller-supplied artifact_root)
  -> separately resolves/checks/opens metadata and optional PNG paths
tests/test_search_page_evidence.py -> search_page_evidence.py
  validate_evidence_fixture(..., optional caller-supplied artifact_root)
  -> may separately resolve/check/open a referenced screenshot
No production collection, adapter, DOM package, dashboard, or application
reader edge was found in the inspected repository source.

Other entry points (separate from evidence helpers)
job_scraper.py __main__ :561–563 -> scrape_jobs() :277
dashboard.py __main__ :252–253 -> main() :242 -> load_jobs()/show_dashboard()
easy_apply.py __main__ :2571 -> main() :2408
application_form.py __main__ :3858 [prints a module heading; not an application workflow entry point]
easy_apply.py imports external_app helpers :12-19; its flow can call
  prepare_external_application_page() :2039 and records outcomes :2050.
```

The reader module contracts describe offline/local evidence preparation and explicitly exclude browser, network, production workflow, output, publication, and application integration. `COLLECTION_EVIDENCE_POLICY.md` likewise describes the collection model and adapter as offline/in-memory and says the readers are a separate security blocker. Conversely, `PHASE_25_EXTERNAL_VALIDATION_READINESS.md` describes a possible later review and integration sequence. These statements support an offline-helper interpretation today and a possible future workflow, but do not establish the owner's product intent or exclude an external host importing the callable functions.

Trust boundaries are distinct:

| Boundary | Source-established behavior | Persistent or external effect / limit |
|---|---|---|
| Collection completion classification | `job_search.py` builds diagnostics/outcomes through the in-memory adapter and classifier. | Classification does not itself prove observed search identity, exhaustion, or all production completeness evidence (policy :87–118, :173–234). |
| In-memory evidence validation | Adapter and DOM package validate supplied data/mappings; DOM references are not opened. | No filesystem containment is obtained from these checks. |
| Filesystem evidence preparation | Reader APIs accept explicit paths/root arguments and perform validation before separate opens (Phase 72 data flow above). | This is the rejected security boundary; no reader design is approved and reads remain blocked. |
| Collection publication | `publish_collection()` rejects all outcomes and returns `False`; atomic CSV writer exists separately. | The inspected publisher does not publish collection results. This is a source fact, not a runtime check. |
| Application and dashboard | Dashboard loads application-tracker data. Application modules contain status/history persistence and browser/form action paths; `execution_policy.py` gates browser actions and persistence on `DRY_RUN`, and submission paths also consult `AUTO_SUBMIT`. | These are separate code paths capable of persistent or external effects when their conditions allow. No such workflow was executed and this review does not verify current process configuration. |

Static search found reader references in their modules, tests, and documentation, with no in-repository production caller, alias, wrapper, callback, dashboard, CLI, scheduler, or application call path. That is not proof of runtime unreachability: external launchers, embedding code, reflection, or code outside the inspected tree remain possible. No `artifact_root` configuration was found in `config.py` or the inspected production collection path; the actual intended source/root is therefore unresolved.

### Intended-role assessment

| Possibility | Supporting evidence | Missing or contrary evidence | Security consequence and decision needed |
|---|---|---|---|
| **A — Future production evidence workflow** | Phase 25 describes later independent review and a possible narrowly scoped production acquisition proposal. Reader APIs and size bounds exist. | Current module contracts explicitly exclude production integration; no production caller or root is configured; publisher remains closed; Phase 66 rejected the current reader design. | Owner must identify the exact workflow, evidence source, caller, and root lifecycle. Any trusted-root use still requires specialist approval, authorized Windows testing, actual results, and a new written implementation decision. |
| **B — Standalone offline utilities** | Both reader docstrings characterize local/offline preparation; tests provide temporary roots; no in-repository production edge was found; policy separates readers from production collection. | No owner statement says they are permanently test/offline-only or defines whether external integrations are prohibited. | Owner must confirm the tools remain isolated, define their supported use and why each limit exists, and identify how the security hold applies to any local file reads. The Phase 66 hold remains until an explicit specialist decision changes its scope; intent alone cannot approve reading. |
| **C — Intent is ambiguous** | The source has offline-only contracts today while readiness/review documents discuss possible later integration; there is no production caller/root or owner decision. | No contradictory source edge resolves the product intent. | This is the current finding. Owner decision is required before selecting an architecture or spending effort on production integration. The existing security review remains necessary for any evidence read subject to the rejected trusted-root boundary. |

### Next-milestone choices

| Alternative | Immediate progress | Required owner decision | Specialist decision / security effect | Dependencies and acceptance |
|---|---|---|---|---|
| Continue investigating intended reader use | Static source/document review is complete for the inspected tree; owner can identify external deployment context. | Name intended caller, evidence source, root lifecycle, and whether an external host exists. | Does not resolve or relax Phase 66. Any trusted-root use remains blocked. | Accept when owner records A/B and the actual deployment boundary; no code change implied. |
| Keep readers isolated and retain the hold | Preserve current separation; unrelated offline work can proceed. | Confirm they are offline utilities and specify permitted scope/size requirements. | Specialist must explicitly clarify whether/when local evidence reads can be allowed; current rejection remains in force. | Accept when isolation intent and any prohibited integrations are written down; reader security criteria still apply before reads are enabled. |
| Request a separately approved production integration design | Draft a workflow-level proposal without implementation. | Identify a real collection caller, evidence source, root owner/lifecycle, and publication needs. | Requires a new specialist-approved security contract before any reader integration; publication remains separately closed. | Define caller/data flow, completion evidence, failure behavior, and non-publication test criteria before implementation proposal. |
| Request specialist review of a proposed Windows-native design | Specialist can review a concrete, owner-grounded contract rather than a speculative API choice. | First supply Gate A environment/threat facts and confirm that production-style file evidence is required. | Specialist must resolve API contract, reparse traversal, object binding, mutation guarantees, support matrix, fail-closed rules, and explicitly authorize next gates. | Then obtain separate test authorization; execute and retain real-Windows evidence per supported configuration; obtain a further written implementation decision. |
| Pause reader work; continue unrelated offline tasks | Work independent of the blocked readers can progress now. | Select a task not dependent on evidence reading or collection publication. | No security decision needed for unrelated work; hold remains unchanged. | Confirm task has no reader, collection, browser, or application side effects and define its own acceptance criteria. |

### Owner decision request

Please decide in writing: **Are `search_page_evidence.py` and `offline_search_evidence.py` intended for production use?** If yes, name the approved workflow/caller, evidence source, and lifecycle/owner of the trusted root. If no, confirm they are to remain isolated offline utilities and state any external integrations that must not call them. In either case, explain the application purpose for the metadata and PNG inputs and whether the current 256 KiB metadata and 10 MiB PNG limits meet that purpose. This is an owner-intent decision only; it is not Windows security approval and does not authorize file reads or implementation.

### Current decision and hold

The current intended-role finding is **C — ambiguous; owner decision required**. The next high-value milestone is that owner decision, followed by the existing Gate A environment/threat register only if a trusted-root evidence workflow is actually required. Do not repeat another general documentation phase before those inputs exist. Phase 66 remains **REJECTED FOR THE CURRENT EVIDENCE-READER DESIGN**: evidence reading remains blocked, collection publication remains closed, `AUTO_SUBMIT` remains false, browser auditing remains disabled, and no security-sensitive implementation is authorized. No runtime workflow or test was run in this phase.

## Phase 91 — generation-storage security review proposal

**Review status: proposed for independent specialist review only. Not an approved design, security finding, implementation authorization, or test authorization.** This section adds a distinct pipeline-generation storage boundary for review. It does not replace or weaken the Phase 66 rejection of the evidence readers. Evidence reading remains blocked; collection publication remains closed; `AUTO_SUBMIT` remains false; browser auditing remains disabled. No production code was changed, and no tests were executed in this phase.

### 1. Proposed workflow and trust boundary

The Phase 88–90 policy proposes separate `job_details` and `job_analyzer` generations. A caller would supply a generation root; a run would create a unique stage/run directory, capture and fingerprint its input, write the stage artifacts and manifest, validate the exact bytes and cross-stage references, publish a terminal manifest, and publish a selection pointer last. A consumer would validate the pointer, referenced manifests, artifact hashes/sizes, and analyzer-to-details binding, then parse the exact bytes it validated. `EMPTY` would explicitly select no candidates; partial/failed/in-progress results would not be selected. Prior generations would be retained for a separately authorized rollback and retention policy.

This is a **proposed workflow**, not existing behavior. `pipeline_generation_store.create_generation()` accepts an explicit caller-supplied root and creates a stage/run directory, but its docstring says this is not a trusted-root or race-safe containment boundary (`pipeline_generation_store.py:129–148`). The helper validates manifests, pointers, fingerprints, and supplied bytes. `read_verified_artifacts()` uses ordinary `Path` joins and `read_bytes()` (`pipeline_generation_store.py:435–455`); its own module documentation disclaims containment, reparse, replacement, and concurrent-writer protection. The helper does not write manifests or pointers, coordinate writers/readers, publish a selected generation, recover interrupted writes, or clean retained generations.

The intended trust boundary therefore remains unresolved at each layer: (1) owner-confirmed root and ancestors; (2) stage and run directory creation; (3) manifest/pointer paths; (4) each artifact path and opened file object; and (5) the exact bytes later parsed by a consumer. A SHA-256 and byte size verify the supplied bytes against metadata; lexical relative-path validation rejects several malformed path strings. Neither establishes filesystem containment, prevents reparse traversal, proves the opened object was contained, prevents concurrent replacement, or makes the read an immutable snapshot.

`output_files.write_replaced_output()` writes one sibling temporary file, flushes and calls `fsync`, then invokes `os.replace`; it explicitly does not promise power-loss durability or a multi-file transaction and says replacement behavior depends on platform/filesystem (`output_files.py:7–42`). It is used for fixed-path outputs today, not as a generation pointer protocol. In particular, there is no implementation evidence here for atomic pointer publication or crash recovery.

### 2. Confirmed facts, proposals, and unresolved assumptions

**Verified from inspected source and tests (static inspection only):**

- The helper is standalone and not wired into production. It defines schema version 1, stages `job_details`/`job_analyzer`, status values, fixed artifact roles, and pointer selection modes.
- Manifest validation checks exact fields, status constraints, accounting reconciliation, required role/path sets, timestamps, and SHA-256/size syntax. `read_artifacts=True` reads and fingerprints artifact bytes and returns them to callers for parsing. The analyzer-binding helper compares supplied details-manifest bytes and details-artifact bytes to the analyzer reference.
- Pointer validation checks pointer shape and selected/latest status consistency. For normal `CURRENT`/`EMPTY` modes, manifest validation is optional at the helper API boundary; a production consumer would have to require and validate the selected and latest manifests and artifacts itself. Explicit rollback requires matching source fingerprints and supplied manifests, but `authorized_by`, `authorization_ref`, and reason are validated as text, not authenticated authorization.
- The generation-store tests contain synthetic cases for schemas, paths, hashes, counts, analyzer binding, pointer disagreement, and rollback-shaped data. One test named `test_mutation_between_artifact_reads_is_detected` exercises an injected fixture condition; it does not demonstrate Windows race resistance or crash consistency.
- Durability tests inject serialization, temporary-file, and replace failures and document that details CSV plus diagnostics are not one transaction. These are unit-level failure tests, not real power-loss, storage-provider, or Windows concurrency tests.

**Proposed requirements for the reviewer to assess:**

- A root must have a defined owner, ACL and ancestor policy, supported provider, privilege context, and threat model. The root must be established by approved means, not inferred from the project directory or a successful path-normalization check.
- Every relevant path component must have a documented reparse policy. The design must explain how the root is anchored, how child components are opened, and how the exact opened objects are tied to validation and bytes consumed.
- All unknown, unsupported, permission-denied, malformed, mismatched, raced, or unverifiable states must return no selected generation and must not fall back to fixed-path CSVs, a weaker path-based check, a directory scan, or stale output.
- Publication ordering, multiple-writer behavior, reader/writer coordination, cleanup safety, crash recovery, and durability must be specified independently. Successful `os.replace`, a content hash, or a passing unit test is not by itself evidence for those properties.

### 3. Specialist questions and acceptance matrix

Every test below is **PROPOSED — NOT RUN**. Real-Windows tests require separate owner authorization before execution. The specialist must identify the exact support cells and reject any configuration for which the required contract cannot be demonstrated.

| Requirement / specialist question | Existing behavior | What remains unproven | Required written specialist decision | Proposed acceptance test and evidence | Expected fail-closed behavior |
|---|---|---|---|---|---|
| **Supported Windows/Python versions, filesystems, storage providers, and privilege levels:** which exact combinations are supportable? | No support matrix is encoded in the helper. Root is caller supplied. | OS build, Python build/architecture, NTFS/ReFS/removable/network/cloud/synchronized provider behavior, privilege and filesystem semantics are not validated for generation storage. | Enumerate supported and rejected matrix cells, version ranges, filesystem/provider assumptions, privileges, and any exclusions. | On each proposed cell, record OS/build, Python version/architecture, volume/provider, ACL/privileges, API and operation results, and test logs. Repeat required tests per cell. | Unsupported or unidentifiable cell: no generation is selected; no fallback to fixed CSVs. |
| **Trusted root, ownership, ACLs, and ancestors:** how is the root established and protected? | `create_generation()` requires an existing caller-provided directory but does not inspect owner, ACLs, parent ACLs, or write principals. | The actual production root is not identified; a project path is not evidence of trust. Writable ancestors or same-account actors may change the namespace. | Specify root identity, owner, ancestor boundaries, ACL requirements, allowed modifying principals, same-account threat model, and root lifecycle. | Inspect ACLs and ownership for the actual owner-designated root and every relevant ancestor; attempt authorized boundary changes as test principals; retain command outputs and effective-token context. | Any missing, ambiguous, unexpectedly writable, or unverifiable root/ancestor condition rejects the operation. |
| **Symlinks, junctions, mount points, and other reparse tags:** what is permitted at the root and each component? | Artifact paths are lexically constrained and fixed to expected names; reads use ordinary path operations. | Lexical checks do not inspect or prevent intermediate reparse traversal, root substitution, or changes after validation. No tag policy is implemented. | Specify allowed/rejected tags, treatment of root itself and ancestors, and a supported method to detect/prevent traversal on every component. | Create controlled reparse points at root, parent, stage, run, and artifact components for every relevant tag/provider; record handle/path identity and sentinel results. | Unexpected or unqueryable reparse state returns no bytes/candidates; never retry through a weaker path. |
| **Safe root-relative opening and exact opened-object binding:** which documented API contract can establish containment? | `read_verified_artifacts()` joins a `Path` and calls `read_bytes()`; the binding helper validates byte strings supplied by a caller. | No root-relative handle-opening contract or handle-to-root containment proof is established. Hashing binds metadata to bytes supplied, not the object’s trusted location. | Identify documented APIs and exact contracts for opening each component relative to an anchored trusted root, reparse controls, and verifying the actual opened object. If no supported contract exists for a cell, reject that cell. | Use instrumented handles and in-root/outside sentinel files; replace each path component between checks/open; capture API traces, handle-derived identity/type, bytes, and sentinel hashes. | If the opened object cannot be proven to meet the root contract, reject it and return no candidate. |
| **Type, identity, size, bounded reads, and content consistency:** how is one validated object tied to the exact bytes parsed? | The helper verifies byte length and SHA-256 after `read_bytes()` and returns bytes. Manifest validation checks declared roles and sizes but does not itself impose a general maximum. | File type/identity on the opened handle, bounded acquisition, and stable content during reading are not guaranteed by the helper. Same-size mutation can evade length-only checks; a hash only fingerprints whichever bytes were read. | Define required handle properties, allowed file types, max sizes, read limits, and the exact snapshot/consistency semantics required. | Test valid files, oversized files, truncation, growth, same-size in-place mutation, type substitution, and replacement while reading; preserve handle/API traces and before/after hashes. | Any type/identity/size/content mismatch or inability to establish a stable read rejects the artifact. |
| **Concurrent replacement and multiple writers:** what races are in scope and how are runs serialized? | Unique run-directory creation uses `mkdir(exist_ok=False)`. There is no lock, writer lease, compare-and-swap, or reader coordination. | UUID directories do not serialize pointer updates, same-root writers, cleanup, or root/component replacement. | Define single-writer versus multi-writer support, lock ownership/lifetime, stale-lock recovery, reader snapshots, and pointer conflict resolution. | Synchronize two writers and readers at generation creation, manifest publication, and pointer update; inject replacement and process termination. Retain traces showing which generation each consumer selects. | Conflict, lost ownership, uncertain writer state, or lock failure yields no new selection; no “last writer wins” assumption without an approved contract. |
| **Pointer publication and failure recovery:** when does a generation become current? | `validate_pointer()` only validates supplied data; it does not serialize, write, replace, or recover a pointer. A manifest can be omitted from normal-mode validation unless the caller enforces it. | No atomic publication, stale-pointer detection, monotonicity, or recovery protocol has been demonstrated. | Specify exact ordering, pointer schema/version transitions, synchronization, whether prior selection remains or clears on failure, and recovery rules at every write boundary. | Force crash/error before and after artifact, terminal manifest, and pointer writes; truncate/corrupt pointer; replay stale pointer; inspect selected state and actual candidate result. | Until all referenced manifests/artifacts and pointer relationships validate, select none; do not scan, infer, or fall back. |
| **Flush, durability, and power loss:** what does “published” survive? | The single-file helper flushes and `fsync`s the temp file before `os.replace`; its docstring disclaims power-loss durability and cross-file transaction guarantees. | Directory-entry persistence, device/provider caches, multi-file ordering, and recovery after actual power loss are not established by source or unit tests. | State the durability level promised and the supported API/filesystem/provider semantics needed to meet it; identify guarantees that cannot be promised. | Authorized crash/power-interruption harness at each publication boundary for every supported cell; retain recovery image/logs and validate pointer, manifests, and artifact hashes after restart. | If durable state is ambiguous or contradictory after restart, no generation is selected until explicit validated recovery. |
| **Retention and cleanup with active readers:** when can old or incomplete generations be removed? | No cleanup/retention code or active-reader tracking exists. | A cleanup process could remove selected/rollback data or race a reader/writer. | Define retention count/age, protected generations, cleanup authority, reader leases/snapshot behavior, and orphan handling. | Hold a reader open during cleanup; race cleanup with new publication and rollback; verify selected and protected generations remain readable and intact. | If active use or protected status cannot be established, do not delete; cleanup failure cannot change selection. |
| **Fail-closed and prohibited fallback behavior:** what happens on every unsupported or unverifiable condition? | Helper raises validation errors for many schema/hash/path inconsistencies. It does not supply a production consumer or comprehensive environment-failure mapping. | No production integration proves every error maps to no candidates; no fallback controls are exercised. | Enumerate all reject conditions and explicitly prohibit fixed-path fallback, weaker path checks, implicit rollback, auto-repair, or candidate discovery by scanning. | Inject missing/invalid manifests, unknown versions/tags, access denied, API-query failure, reparse points, races, unsupported providers, corrupt pointers, and stale outputs; capture returned candidate count and logs. | Every uncertain condition produces zero candidates and no publication; retain diagnostic reason without using unverified content. |

### 4. Existing test evidence and its limits

The inspected helper tests include schema/status validation, path syntax, artifact hash/size mismatch, analyzer binding, pointer mismatch, rollback fields, and a fixture-level mutation test (`tests/test_pipeline_generation_store.py`). The inspected durability tests include serialization and replace failures and explicitly demonstrate that details CSV and diagnostics replacement are not a pair transaction (`tests/test_csv_output_durability.py`). They are source evidence only in this phase; they were not executed. They do not establish Windows reparse resistance, trusted-root containment, handle identity, concurrent race guarantees, pointer publication, power-loss durability, or behavior on every supported storage provider.

### 5. Evidence required before reconsidering production integration

1. Owner-confirmed intended workflow and producer; exact root path, owner, ACLs, ancestor protections, modifying principals, same-account threat scope, concurrency assumptions, and retention needs.
2. A written supported-environment matrix covering Windows build, Python version/architecture, filesystem and storage provider, privilege context, and excluded configurations.
3. A new independent specialist decision identifying the documented API contract, component/reparse rules, opened-object binding, content consistency, synchronization, pointer publication/recovery, durability limits, and mandatory fail-closed behavior. API availability or names alone are insufficient.
4. Separate explicit owner authorization for real-Windows acceptance testing. Tests must run on every proposed supported environment and retain commands, environment inventory, traces, inputs, outputs, hashes, failure-injection points, and post-restart recovery evidence.
5. Reviewed passing results against predeclared criteria, including negative/fail-closed cases. A failed or unrun cell must be excluded from support.
6. A further written specialist decision based on the design and actual acceptance evidence that explicitly approves, conditionally approves with bounded prerequisites, or rejects implementation. Any implementation authorization must be separate and explicit.

Until all applicable evidence and decisions exist, the generation-store helper remains isolated, the evidence readers remain blocked, collection publication remains closed, and production integration is **NO-GO**.

## Phase 93 — security acceptance criteria refinement

**Documentation-only proposal. All criteria below are proposed and NOT RUN.** This section makes the Phase 91 matrix more testable; it does not approve an API, support cell, test execution, implementation, or production use. The Phase 66 rejection and collection-publication hold remain unchanged. The actual root, supported environment, threat model, and authorization mechanism remain **UNRESOLVED**.

### Test classes and authorization boundary

- **A — isolated unit tests:** synthetic manifests, pointers, byte arrays, and temporary test roots. These can validate deterministic schema/consumer decisions after an implementation exists. They do not establish Windows containment, ACL enforcement, reparse resistance, race safety, or durability. No tests are authorized or run by this documentation phase.
- **B — controlled Windows acceptance tests:** filesystem/API behavior on a disposable test root in each exact owner-approved support-matrix cell. Retain the environment inventory and logs. No candidate support cell is currently approved.
- **C — specialist preapproval required:** adversarial tests that change ACLs, create reparse points, race path components or contents, run multiple processes, terminate at write boundaries, simulate power loss, or exercise real credentials/authorization. A specialist must approve the test design and safety boundary before execution. Use isolated disposable fixtures; never inject faults into protected project data or a production root.

Tests may be both **B and C**. An isolated unit test is not a substitute for its corresponding Windows acceptance case. All tests below remain **NOT RUN**.

### Explicit acceptance-test specifications

For every Windows test, the configuration field means: **repeat on every exact supported Windows build, Python version/architecture, filesystem/storage provider, and privilege cell after written approval. No cell is currently approved.** The specialist must identify any exclusions before test execution.

| Test / class | Preconditions and configuration | Controlled condition | Expected observable result | Evidence and logs to retain | Exact pass / fail criterion | Required fail-closed behavior |
|---|---|---|---|---|---|---|
| **1. Trusted-root identity and ACL enforcement** — B, C | Owner has identified the exact root and ancestors; specialist/owner have approved the principal list, threat model, and ACL criteria; isolated disposable test root; named test identities and effective-token context. | Inspect the actual designated root read-only; in the disposable copy, attempt only pre-authorized create, replace, rename, delete, and reparse operations as each approved and unapproved principal. | Effective access matches the approved matrix at the root and every ancestor; authorized writer behavior is limited to the approved scope; unauthorized principals cannot alter the namespace. | Root/ancestor identities, owners, ACLs, inheritance, effective tokens, principal IDs, commands, access results, and test-root inventory. | **Pass:** every principal’s observed rights match the written ACL contract, and no disallowed principal can change root/ancestor entries in the disposable fixture. **Fail:** root/ancestor identity is ambiguous, any unapproved write/rename/delete/reparse right exists, or evidence is incomplete. | Do not create or select a generation if root identity, ACL state, or a required security query cannot be verified. Never infer trust from the project path or successful normalization. |
| **2. Reparse traversal and component replacement** — B, C | Approved root-relative opening contract and complete per-component tag policy; disposable in-root and outside-root sentinels; supported Windows cell and approved synchronization harness. Specialist must enumerate relevant tags (including symlink, junction, mount point, and any additional supported reparse tags). | Place controlled reparse points at root, ancestor, stage, generation, and artifact components; replace a component after validation and immediately before/during opening. Include replacement with a same-size outside sentinel. | Each attempt either reads the specific authorized in-root target under the approved contract or rejects. Outside sentinel bytes are never returned as accepted evidence. | Tag/type inventory, component-by-component trace, synchronization points, handle-derived identity, sentinel fingerprints, return status, and exception/query results. | **Pass:** for every tag and race point, accepted bytes map to the permitted object and every rejected/query-failure case returns no artifact. **Fail:** any outside sentinel is accepted, component traversal is unobserved, or a race produces an unverified read. | Any unexpected tag, failed tag query, root/component swap, or inconclusive containment check returns no bytes/candidates; no path-based retry. |
| **3. Opened-object identity and exact-byte binding** — B, C; A for pure byte comparison | Specialist has defined the required object identity/type evidence, bounded-read behavior, and parser contract; disposable fixture with distinct in-root/outside contents; approved handle instrumentation. | Replace the leaf before/during open; mutate path after handle acquisition; change a different same-size file; attempt to cause validation and parsing to use separate reads. | Consumer parses only bytes read from the validated open object. If the required identity cannot be bound to the bytes, it rejects. | Handle/object identity and file-type observations, open/read event trace, exact byte buffer fingerprint, manifest and artifact fingerprints, parser input fingerprint, and sentinel result. | **Pass:** the bytes parsed equal the exact bytes fingerprinted from the object whose identity/type passed the approved contract; replacement cannot redirect the handle; otherwise operation rejects. **Fail:** parser reopens the path, consumes different bytes, or identity evidence is missing/contradictory. | No path reopen or weaker check after validation; inability to prove object-to-byte binding means zero candidates. |
| **4. Truncation, growth, and same-size mutation** — B, C; A for deterministic byte/hash mismatch | Approved snapshot/consistency semantics, size bound, and mutation test hook; disposable fixture and controlled writer. | Truncate, extend, overwrite same-size ranges, and mutate before/during/after reading at synchronized points. Include growth beyond the approved bound. | Either the reader obtains one coherent permitted snapshot matching the approved identity/hash/size contract, or the operation rejects. It must not accept a mixture or content that fails the selected consistency rule. | Mutation schedule, writer/reader traces, sizes and hashes before/after, exact returned/parsed bytes, handle information, and status. | **Pass:** every attempt either returns a coherent snapshot satisfying all approved checks or rejects; over-limit, mixed, or contradictory bytes are always rejected. **Fail:** changed/mixed/over-limit bytes are accepted or the result cannot be classified. | On detected mutation, growth beyond limit, short read, or uncertain snapshot semantics, return no bytes/candidates; do not retry with weaker path access. |
| **5. Concurrent readers and writers** — B, C | Approved publication protocol, reader snapshot/lease rule, and decision on whether old selection remains visible; isolated generations with distinct content fingerprints. | Hold readers while a writer writes artifacts, terminal manifest, and pointer; run readers before/during/after publication and inject controlled delays/failures. | Each reader sees a fully validated eligible old generation, a fully validated eligible new generation, or no selection. No reader observes a mixed manifest/artifact/details-analysis generation. | Per-process timeline, selected run ID, every referenced manifest/artifact hash, open-handle trace, and candidate result for each reader. | **Pass:** every observed selected generation is internally complete and correctly cross-bound, or selection is empty; no mixed pair or partial generation is observed. **Fail:** any mixed, torn, or unvalidated generation is returned. | If a consistent reader snapshot cannot be established, return no candidates; do not retry by mixing old and new files. |
| **6. Multiple writers and pointer-update conflicts** — B, C | Approved writer serialization or conflict protocol and stale-writer handling; two or more isolated writer processes with unique runs and controlled barriers. | Synchronize writers at attempt registration, artifact completion, terminal manifest, and pointer publication; force stale reads and competing updates. | The selected pointer follows the approved serialization/conflict policy. A losing or stale writer cannot silently overwrite a newer valid selection or publish a mixed state. | Process IDs, lock/lease ownership and lifetime, pointer versions/bytes, before/after manifests, event order, and each writer’s result. | **Pass:** one defined winner/order is observed or the conflicting update is rejected; pointer references one fully validated generation and no accepted update is lost contrary to policy. **Fail:** silent last-writer-wins, lost update, inconsistent pointer, or unresolved lock ownership. | On lock/lease loss, stale pointer, or conflict, publish no selection from the uncertain writer; never infer a winner. |
| **7. Interrupted publication and recovery** — B, C; A for injected state-machine tests | Approved write ordering and prior-selection policy; disposable root; fault injector or controlled process termination at each boundary. | Interrupt before generation creation; after attempt publication; during each artifact temp write; after one/all artifacts; after terminal manifest; during pointer temp write/replace; immediately after pointer publication. | On restart, either the previously approved complete selection remains valid (if that policy is approved), the new complete generation is selected after successful pointer publication, or no generation is selected. Incomplete attempts never become candidates. | Fault point, process exit/restart logs, directory inventory, pointer and manifest bytes, all artifact hashes/sizes, recovery action, and actual consumer candidate result. | **Pass:** for every boundary, recovery matches the approved state transition exactly; never mixed, guessed, or incomplete. **Fail:** partial generation is selected, a stale pointer is accepted, or recovery behavior is undocumented. | Missing, malformed, contradictory, or interrupted state selects none until explicit validated recovery; no directory scan or fixed-path fallback. |
| **8. Crash and durability behavior** — B, C | Specialist has stated the durability level and the owner has approved the provider-specific test method; disposable environment and recoverable test image/device. | Process crash at each write boundary; separately perform only the specialist-approved power-loss/cache interruption scenarios. | Recovered state satisfies the declared durability guarantee; otherwise it is rejected and requires explicit recovery. | Storage/provider details, write/flush/replace sequence, interruption method, restart inventory, recovered pointer/manifest/artifact hashes, system logs, and deviations. | **Pass:** all supported-cell trials recover a state permitted by the written durability contract with no mixed or corrupt selection. **Fail:** any result contradicts the contract or evidence cannot establish the outcome. | If durability cannot be established, exclude the cell or keep selection disabled; do not describe `fsync`/`os.replace` success as a power-loss guarantee. |
| **9. Cleanup during active reads/writes** — B, C; A for retention policy logic | Approved retention policy, protected-generation list, cleanup authority, and reader/writer coordination protocol; disposable root. | Start a reader holding a generation and a writer publishing one; run cleanup against selected, rollback-protected, in-progress, and orphan generations. | Cleanup defers/refuses active or protected generations. Readers complete from a valid snapshot or fail closed; cleanup never changes the selected pointer or removes its artifacts. | Candidate set before/after, protected IDs, active reader/writer state, cleanup logs/authority, hashes, and reader results. | **Pass:** no selected/protected/active generation is removed or altered; cleanup affects only eligible generations under the approved policy. **Fail:** a reader loses or mixes data, selected artifacts disappear, or cleanup races are unresolved. | If activity/protection cannot be proven, perform no deletion; selection remains unchanged or disabled if its artifacts cannot be verified. |
| **10. Legacy-only and mixed-mode rejection** — A; B for consumer integration | Owner-approved enforcement mode and a manifest-aware consumer implementation exist; isolated synthetic CSV/manifest fixtures. | Present only legacy fixed-path CSVs; present generation-backed details with legacy analysis; reverse the mix; omit/corrupt pointer or manifest while legacy files remain. | Under enforcement, only one explicitly declared, fully validated generation chain is eligible. Legacy-only or mixed-mode inputs produce zero candidates; legacy files are not parsed as a fallback. | Fixture inventory and hashes, consumer path/open trace, manifest/pointer validation result, candidate count, and diagnostic reason. | **Pass:** each legacy-only/mixed/corrupt case yields zero candidates with no legacy fallback read; valid all-generation control case reads only the selected bytes. **Fail:** any candidate is derived from unverified legacy/mixed data. | No automatic fallback, migration, adoption, directory scan, or “best available” file selection. |
| **11. Rollback authorization and source mismatch** — A for decision validation; B, C for real authorization/persistence | Owner has approved an authorization mechanism, eligible approvers, same-source rule, and audit record format; isolated prior `COMPLETE` and failed/partial attempt. | Try no authorization, malformed/unverifiable authorization, unauthorized identity, wrong prior manifest, changed source fingerprint, and a valid authorized same-source rollback. | Only the approved actor/mechanism can select a validated prior `COMPLETE` generation; changed-source rollback is rejected unless explicitly approved by owner and specialist with documented stale-data consequences. | Authenticated principal/approval evidence, authorization reference verification, source and generation fingerprints, manifests/artifacts, pointer before/after, and consumer outcome. | **Pass:** unauthorized/missing/malformed authorization and source mismatch always reject; only a verifiable approved event selecting a matching validated generation succeeds. **Fail:** nonempty strings alone authorize rollback, stale source is selected contrary to policy, or audit evidence is incomplete. | No implicit rollback. Any unverifiable authority, source mismatch, or prior-generation inconsistency selects none. |
| **12. Storage-boundary query/verification failure** — A for injected error mapping; B, C for real platform/API failures | Approved support cell and list of required security queries; controlled fixture for injected errors and approved Windows harness. | Force access denied, unsupported provider, failed identity/type/reparse query, missing root, or API failure at each required verification step. | Every required verification either succeeds under the approved contract or causes an explicit rejection; no unverified condition is treated as safe. | Injected and real error codes, query sequence, environment cell, logs, selected ID, and candidate result. | **Pass:** every required-query failure yields no selected generation and a precise diagnostic; supported positive control still validates. **Fail:** any query failure is ignored or followed by weaker fallback. | No selection whenever the storage boundary cannot be verified. |

### Acceptance evidence and unresolved gates

- The **actual artifact root, Windows product/build, Python version/architecture, filesystem/provider, privileges, and threat model remain unresolved or unapproved**. Historical environment notes include a Windows product-label discrepancy; they do not establish the supported matrix.
- The **authorization mechanism remains unresolved**. Helper rollback strings are not proof of identity or approval.
- All Windows tests require a predeclared cell inventory and written pass criteria. A result applies only to the tested cell; no generalization to another build/provider is permitted without specialist review.
- Isolated unit tests can verify schema, hash comparison, fallback decisions, and state-machine behavior. They cannot pass the Windows security gate.
- Controlled Windows tests require separate owner authorization. Tests classified C also require specialist approval of the method and safety boundary before execution. Do not use the project’s protected files or a production root as adversarial fixtures.
- Retain exact commands, test harness/version, test IDs, timestamps, environment inventory, principal/privilege details, fault schedule, logs/traces, before/after hashes, pointer/manifest/artifact snapshots, consumer result, and per-cell PASS/FAIL/BLOCKED/NOT RUN outcome. Any failed or unrun required case blocks that support cell.

This refinement provides proposed pass/fail criteria only. It does not authorize tests or implementation. Evidence reading remains blocked, collection publication remains closed, and production integration remains **NO-GO**.
