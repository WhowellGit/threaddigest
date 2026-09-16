# Synthetic wire-shaped fixtures (placeholders)

Every file here is a **hand-written, synthetic** stand-in for the `data` object of a
Reddit listing child (`t3` for posts, `t1` for comments). Ids, users, subreddit ids,
scores and timestamps are invented; no real Reddit content is present.

They exist so the M0 `core.normalize` and `core.themes` unit tests have realistic key
sets to work against. **In M1a they are to be replaced by real captures made with
`threaddigest probe <fullname> --save-fixture`** (scrubbed of personal data), keeping the
same filenames so the tests keep running. Until then, any field semantics asserted from
these files are hypotheses about Reddit's wire format, not observations.

| File | Exercises |
|---|---|
| `post_link.json` | Link post: `is_self` false, external `domain`, `post_hint` `link`, `edited` false, every optional key present |
| `post_self.json` | Self post: markdown body (bold, list, table, raw `<script>` to be escaped), `edited` as a float epoch, mixed-case `subreddit` (`VideoEditing`), `is_gallery` absent |
| `post_deleted_link.json` | Author-deleted link post: `author` `"[deleted]"`, no `author_fullname` key, `removed_by_category` `"deleted"`, empty `selftext` |
| `comment.json` | Top-level comment (`parent_id` is the `t3_` post), `depth` 0, `replies` as the empty string |
| `comment_deleted.json` | Deleted reply: `author` `"[deleted]"`, `body` `"[deleted]"`, no `author_fullname`, `collapsed_reason_code` `DELETED`, `depth` 1 |
