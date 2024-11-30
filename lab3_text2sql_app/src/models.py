def calculate_cost_from_tokens(tokens, model_id):
    PRICING = {
        "anthropic.claude-3-5-sonnet-20240620-v1:0": {
            "input_rate": 0.003,
            "output_rate": 0.015
        },
        "anthropic.claude-3-5-sonnet-20241022-v2:0": {
            "input_rate": 0.003,
            "output_rate": 0.015
        },
        "anthropic.claude-3-5-haiku-20241022-v1:0": {
            "input_rate": 0.0005,
            "output_rate": 0.0025
        },
    }
    if model_id not in PRICING:
        return 0.0, 0.0, 0.0 
    
    input_cost = tokens['total_input_tokens'] / 1000 * PRICING[model_id]['input_rate']
    output_cost = tokens['total_output_tokens'] / 1000 * PRICING[model_id]['output_rate']
    total_cost = input_cost + output_cost

    return input_cost, output_cost, total_cost


