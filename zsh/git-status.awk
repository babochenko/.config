{
  ins = $1; del = $2
  path = ""; for (i=3; i<=NF; i++) path = path (i>3 ? " " : "") $i
  n = split(path, parts, "/"); filename = parts[n]
  dir = ""; for (i=1; i<n; i++) dir = dir (i>1 ? "/" : "") parts[i]
  if (length(dir) > 66) dir = ".../" substr(dir, length(dir) - 62)
  if (path ~ /src\/main/) grp = 2
  else if (path ~ /src\/test/) grp = 3
  else grp = 1
  g_count[grp]++
  idx = g_count[grp]
  g_rows[grp, idx] = ins "\t" del "\t" filename "\t" dir
  g_names[grp, idx] = filename
  w = length(ins+0) + 1; if (w > max_ins) max_ins = w
  w = length(del+0) + 1; if (w > max_del) max_del = w
  t_ins += ins+0; t_del += del+0
  t_files++
}
END {
  if (t_files > 0) {
    grn = "\033[32m"; red = "\033[31m"; gry = "\033[38;5;244m\033[3m"; rst = "\033[0m"
    if (t_files > 1)
      printf " %d files changed: %s+%d%s %s-%d%s\n", t_files, grn, t_ins, rst, red, t_del, rst
    else
      printf " 1 file changed\n"
    g_label[1] = ""; g_label[2] = "main"; g_label[3] = "test"
    for (g = 1; g <= 3; g++) {
      count = g_count[g]
      if (!count) continue
      if (g > 1) printf "\n"
      if (g_label[g] != "") printf " %s:\n", g_label[g]
      for (i = 1; i <= count; i++)
        for (j = i + 1; j <= count; j++)
          if (g_names[g, j] < g_names[g, i]) {
            tmp = g_rows[g, i]; g_rows[g, i] = g_rows[g, j]; g_rows[g, j] = tmp
            tmp = g_names[g, i]; g_names[g, i] = g_names[g, j]; g_names[g, j] = tmp
          }
      for (i = 1; i <= count; i++) {
        split(g_rows[g, i], f, "\t")
        ins = f[1]+0; del = f[2]+0; filename = f[3]; dir = f[4]
        plus = (ins > 0) ? grn "+" sprintf("%-*d", max_ins-1, ins) rst : sprintf("%*s", max_ins, "")
        minus = (del > 0) ? red "-" sprintf("%-*d", max_del-1, del) rst : sprintf("%*s", max_del, "")
        printf "  %s %s %s %s(%s/)%s\n", plus, minus, filename, gry, dir, rst
      }
    }
  }
}
