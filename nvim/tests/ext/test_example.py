def test_addition():
    """Test basic addition"""
    assert 1 + 1 == 2
    assert 5 + 3 == 8

def test_subtraction():
    """Test basic subtraction"""
    assert 5 - 3 == 2
    assert 10 - 4 == 6

def test_multiplication():
    """Test basic multiplication"""
    assert 2 * 3 == 6
    assert 4 * 5 == 20

def test_division():
    """Test basic division"""
    assert 10 / 2 == 5
    assert 15 / 3 == 5

def test_string_operations():
    """Test string operations"""
    assert "hello" + " world" == "hello world"
    assert "test".upper() == "TEST"

def test_list_operations():
    """Test list operations"""
    test_list = [1, 2, 3]
    test_list.append(4)
    assert len(test_list) == 4
    assert test_list[-1] == 4

def not_a_test_function():
    """This should not be detected as a test"""
    return "not a test"