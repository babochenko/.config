local M = require 'ext/mymath'

describe("evaluates", function()
  it("sum", function()
    assert.equals("Result: 3", M._eval({ text = "1+2" }))
  end)
  it("sum with spaces", function()
    assert.equals("Result: 3", M._eval({ text = "1 + 2" }))
  end)
  it("sum with fpoints", function()
    assert.equals("Result: 3.5", M._eval({ text = "1.2 + 2.3" }))
  end)
  it("complex expression", function()
    assert.equals("Result: 1.275", M._eval({ text = "((1.05 * 2) + 3) / 4" }))
  end)
end)

