# Testing Guide - AURUM Trading System

## Overview

AURUM includes comprehensive unit and integration tests for validating MT4 bridge operations and Claude agent behavior.

## Test Structure

```
src/tests/
├── unit/
│   ├── test_mt4_bridge.py          # MT4 bridge unit tests (mocked)
│   └── test_claude_bridge.py       # Claude CLI integration tests
└── integration/
    └── test_mt4_connection.py      # MT4 live connection tests
```

## Unit Tests for MT4 Trading Operations

### Location
`src/tests/unit/test_mt4_bridge.py`

### Coverage

#### 1. Connection Tests
- **test_connect_success**: Verify successful TCP connection to MT4
- **test_connect_failure**: Verify proper error handling on connection failure
- **test_ping_success**: Verify PING command works
- **test_ping_timeout**: Verify timeout handling
- **test_not_connected_error**: Verify error when not connected

#### 2. Order Operations Tests
- **test_buy_order_success**: BUY order execution and ticket retrieval
- **test_buy_order_error**: BUY order failure (e.g., insufficient funds)
- **test_sell_order_success**: SELL order execution
- **test_sell_order_error**: SELL order failure handling
- **test_close_position_success**: Close position by ticket
- **test_close_position_error**: Handle closing non-existent position

#### 3. Position Modification Tests
- **test_modify_sl_tp**: Modify Stop Loss and Take Profit
- **test_timeframe_change**: Change chart timeframe
- **test_timeframe_change_multiple_periods**: Test all supported timeframes (M1, M5, M15, M30, H1, H4, D1, W1, MN1)

#### 4. Status Query Tests
- **test_status_no_orders**: Query status with no open positions
- **test_status_with_orders**: Query status with open positions

#### 5. Error Handling Tests
- **test_invalid_response_format**: Handle invalid MT4 responses
- **test_empty_response**: Handle connection closure
- **test_invalid_ticket_format**: Handle malformed ticket responses
- **test_socket_error_on_send**: Handle socket errors during transmission

#### 6. Context Manager Tests
- **test_context_manager**: Verify context manager (`with` statement) support

#### 7. Paper Trading Scenarios
- **test_full_trade_cycle_buy_and_close**: BUY → MODIFY → CLOSE workflow
- **test_full_trade_cycle_sell_and_close**: SELL → MODIFY → CLOSE workflow
- **test_multiple_concurrent_positions**: Manage multiple positions simultaneously

## Running Tests

### Run all unit tests
```bash
pytest src/tests/unit/ -v
```

### Run only MT4 bridge tests
```bash
pytest src/tests/unit/test_mt4_bridge.py -v
```

### Run specific test class
```bash
pytest src/tests/unit/test_mt4_bridge.py::TestMT4BridgePaperTradingScenarios -v
```

### Run specific test
```bash
pytest src/tests/unit/test_mt4_bridge.py::TestMT4BridgePaperTradingScenarios::test_full_trade_cycle_buy_and_close -v
```

### Run with coverage report
```bash
pytest src/tests/unit/test_mt4_bridge.py --cov=src.mt4 --cov-report=html
```

### Run integration tests (requires MT4 running)
```bash
pytest src/tests/integration/ -m mt4 -v
```

## Test Architecture

All unit tests use **mocked socket connections** via `unittest.mock.patch()`:

- No MT4 platform required for unit tests
- Fast execution (~0.14s for all 23 tests)
- Predictable behavior with controlled responses
- Tests real error conditions safely

### Mock Response Format

MT4 responses follow the format:
```
OK|<data>              # Success
ERROR|<code>|<msg>    # Failure
```

Example mocked responses:
```python
"OK|123456\n"           # BUY returns ticket
"OK|closed\n"           # CLOSE returns status
"ERROR|130|..."         # Error code 130: Insufficient funds
```

## Integration Tests

Integration tests in `src/tests/integration/test_mt4_connection.py` require:
1. AURUM_Bridge.mq4 running in MT4
2. MT4 listening on 127.0.0.1:5555
3. Paper trading account active

Run with:
```bash
pytest src/tests/integration/ -m mt4
```

## Continuous Integration

Add to CI/CD pipeline:
```yaml
- name: Run unit tests
  run: pytest src/tests/unit/ -v --tb=short
  
- name: Run integration tests (if MT4 available)
  run: pytest src/tests/integration/ -m mt4
```

## Common Issues

### ModuleNotFoundError
Ensure pytest is run from repository root:
```bash
cd /path/to/atenea-aurum
pytest src/tests/unit/test_mt4_bridge.py
```

### Socket import errors
If using different Python versions, ensure socket module is available (standard library, always included).

### MT4 Connection Issues (Integration Tests)
- Verify EA is running in MT4
- Check MT4 server address: `127.0.0.1:5555`
- Check MT4 firewall rules
- Review AURUM_Bridge.mq4 logs

## Test Development Guidelines

When adding new MT4 operations:

1. Create unit test with mocked socket
2. Mock the response sequence
3. Test success and error cases
4. Test edge cases (invalid data, timeouts, etc.)
5. Add integration test if requires live MT4

Example test template:
```python
@patch("src.mt4.bridge.socket.socket")
def test_new_operation(self, mock_socket_class):
    mock_sock = MagicMock()
    mock_file = MagicMock()
    mock_file.readline.return_value = "OK|success\n"
    mock_sock.makefile.return_value = mock_file
    mock_socket_class.return_value = mock_sock

    bridge = MT4Bridge()
    bridge.connect()
    result = bridge.new_operation(params)
    
    assert result["ok"] is True
```
