# Issue #157 — Fleet patterns (pointer)

Private GitHub Issue: `matthewhand/open-swarm-private#157` (FLEET-PATTERNS).

This file is a **pointer / note only** (`Refs #157`). It does **not**
land or close the fleet Success checklist.

## Success(1) remote prove — OpenSSH argv space-join

OpenSSH concatenates the remote command argv with spaces; the remote
login shell then parses that string.

- Multiline `python3 -c` helpers break (`Argument expected for the -c
  option`) unless each argv element is shell-quoted (`shlex.quote`) or
  the hop is one quoted remote string.
- Stub runners that `exec` the argv **list** after `--` hide this.
  `bash -c` of the space-joined string is the honest check.
- Same class will bite **Rakazo / OpenMousBot remote drive** and
  **Herdr SSH**.

`software_dev` (#148) now quotes the hop and has
`test_openssh_space_join_requires_quoted_remote_argv`. That is a
pattern note for the fleet checklist, not a claim that #157 Success(1)
is done.

See [ISSUE-148-software-dev-remote-workdir.md](./ISSUE-148-software-dev-remote-workdir.md).
