import datetime
import json
import logging

import find_bin_day as fbd


def convertor(o):
    if isinstance(o, datetime.date):
        return o.isoformat()
    raise TypeError(f"dont support {type(o)}")


def lambda_handler(event, context):

    logging.getLogger().setLevel(logging.INFO)

    post_code = event["post_code"]
    house_number = event["house_number"]

    cache = fbd.NoCacheCache()
    page = fbd.BinWebPage(cache)
    dates = page.find_dates(post_code, house_number)

    result = {
        'statusCode': 200,
        'body': json.dumps(dates, default=convertor)
    }

    return result
