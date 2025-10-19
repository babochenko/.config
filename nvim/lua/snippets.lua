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

  if db_name == "authentication" then
    snippets = concat(snippets, {
      s("devices", t_multiline([[
        select id, last_used_date, state, brand, app_name, device_token
        from devices
        where 1 = 1
        -- and owner_id = ''
        -- and brand = 'Apple'
        -- and brand = 'Browser'
        -- and state = 'ACTIVE'
        order by last_used_date desc
      ]])),
    })

  elseif db_name == 'market-comms' then
    snippets = concat(snippets, {
        s('recipients', t_multiline([[
            select * from notification_recipients
            where 1 = 1
            -- and user_id = ''
            -- and base_currency = ''
            order by created_date desc
        ]])),
    })

  elseif db_name == 'hermes_central' then
    snippets = concat(snippets, {
        s('push_messages', t_multiline([[
            select dispatch_metadata, * from push_message
            where 1 = 1
            and from_service = 'market-comms'
            -- and user_id = '7c8657f4-6de7-4e64-b42b-446557713609'
            and created_date > now() - interval '2 hour'
            order by created_date desc
        ]])),
    })

  end
  
  return snippets
end

vim.api.nvim_create_autocmd("FileType", {
  pattern = "sql",
  callback = function()
    snip.add_snippets("sql", sql_snippets())
  end,
})

