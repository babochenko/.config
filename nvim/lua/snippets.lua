local path = os.getenv("NVIM_SNIPPETS_PATH")
local snip_add = nil

local function try_load(p)
  if not p or p == "" then return nil end
  if p:match("%.lua$") then
    local f = loadfile(p); if not f then return nil end
    local ok, mod = pcall(f)
    return ok and mod or nil
  else
    local ok, mod = pcall(require, p)
    return ok and mod or nil
  end
end

local snip_add = try_load(path)
    or try_load("snippets_add")
    or {
        additional_sql_snippets = function(s, _) return s end
    }

local snip = require("luasnip")
local s = snip.snippet
local t = snip.text_node
local f = snip.function_node

local function t_multiline(str)
  -- Split into lines
  local lines = vim.split(str, "\n", { trimempty = true })
  if #lines == 0 then return t({}) end

  -- Find indent of first non-empty line
  local first_line = lines[1]
  local first_indent = #first_line:match("^(%s*)")

  -- Trim that exact indent from all lines
  for i, line in ipairs(lines) do
    lines[i] = line:sub(first_indent + 1)
  end

  return t(lines)
end

local function get_db()
  local db = vim.b.db or ""
  return db:match(".*/([^/?]+)$") or ""
end

local function concat(a, b)
  local result = {}
  for i = 1, #a do
    result[#result+1] = a[i]
  end
  for i = 1, #b do
    result[#result+1] = b[i]
  end
  return result
end

snip.add_snippets("python", {
  s("main", t({
    'if __name__ == "__main__":',
    '    ',
  })),
})

local function sql_snippets()
  local snippets = {
      s('1d', t({ "and created_date > now() - interval '1 day'" })),
      s('json', t_multiline([[
        SELECT json_agg(t) AS data
        FROM (

        ) AS t;
      ]])),
  }

  local db_name = get_db()
  vim.g.db = db_name

  snippets = snip_add.additional_sql_snippets(snippets, db_name)
  
  return snippets
end

vim.api.nvim_create_autocmd("FileType", {
  pattern = "sql",
  callback = function()
    snip.add_snippets("sql", sql_snippets())
  end,
})

