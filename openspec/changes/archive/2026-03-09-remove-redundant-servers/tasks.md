## 1. Remove server definitions from axios

- [x] 1.1 Remove `filesystem` server block from `~/Projects/axios/home/ai/mcp.nix`
- [x] 1.2 Remove `git` server block from `~/Projects/axios/home/ai/mcp.nix`
- [x] 1.3 Remove `nix-devshell-mcp` server block from `~/Projects/axios/home/ai/mcp.nix`
- [x] 1.4 Remove `sequential-thinking` server block from `~/Projects/axios/home/ai/mcp.nix`

## 2. Update autoEnable and dependencies

- [x] 2.1 Remove `"git"` and `"filesystem"` from the `autoEnable` list in `~/Projects/axios/home/ai/mcp.nix`
- [x] 2.2 Remove `nix-devshell-mcp` from `home.packages` list in `~/Projects/axios/home/ai/mcp.nix`

## 3. Update documentation

- [x] 3.1 Update `CLAUDE.md` module usage example to reference a remaining server instead of `git`
- [x] 3.2 Review and update any other docs referencing removed servers

## 4. Verify

- [x] 4.1 Confirm remaining server list is correct: github, time, context7, axios-ai-mail, mcp-dav, brave-search, journal
