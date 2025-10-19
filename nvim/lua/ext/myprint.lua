local function _print(tbl, indent)
    if not indent then indent = 0 end
    local toStr = ""
    local formatting = string.rep("  ", indent)

    for k, v in pairs(tbl) do
        if type(v) == "table" then
            toStr = toStr .. formatting .. tostring(k) .. ":\n" .. _print(v, indent + 1)
        else
            toStr = toStr .. formatting .. tostring(k) .. ": " .. tostring(v) .. "\n"
        end
    end
    print(toStr)
end

return {
  _print = _print,
}

