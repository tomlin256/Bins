#!/bin/zsh

zip -g function.zip find_bin_day.py
zip -g function.zip lambda_function.py
aws lambda update-function-code --function-name alexa_get_bin_days --zip-file fileb://function.zip
