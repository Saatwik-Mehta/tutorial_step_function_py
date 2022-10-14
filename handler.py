import json
import boto3
import logging

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

dynamo_db = boto3.resource("dynamodb", "ap-south-1")
book_table = dynamo_db.Table("bookTable")
user_table = dynamo_db.Table("userTable")
step_function = boto3.client('stepfunctions')


class BookOutOfStockError(Exception):
    def __init__(self):
        self.name = "BookOutOfStockError"

    def __repr__(self):
        return self.name


class BookNotFoundError(KeyError):
    def __init__(self):
        self.name = "BookNotFoundError"

    def __repr__(self):
        return self.name


def is_book_available(book, quantity):
    return book["quantity"] - quantity > 0


def deductPoints(user_id):
    user_table.update_item(Key={
        "userId": user_id
    },
        UpdateExpression='SET points= :new_points',
        ExpressionAttributeValues={
            ':new_points': 0
        }
    )


def checkInventory(data, context):
    LOGGER.info("datainput: %s", data)
    print(data)
    try:
        result = book_table.get_item(Key={"bookId": data["bookId"]})
        print(result)
        if result.get('Item'):
            book_details = result['Item']
        else:
            raise BookNotFoundError
        LOGGER.info("book details:%s", book_details)
        if is_book_available(book_details, data["quantity"]):
            return book_details
        else:
            raise BookOutOfStockError

    except BookOutOfStockError as oos_error:
        raise BookOutOfStockError
    except BookNotFoundError as not_found_error:
        raise BookNotFoundError


def calculateTotal(data, context):
    LOGGER.info(context.function_name)
    LOGGER.info("Inputs %s", data)
    total = data["book_details"]["price"] * data["quantity"]
    return dict(total_price=total)


def redeemPoints(data, context):
    LOGGER.info(context.function_name)
    LOGGER.info("Inputs %s", data)
    total_price = data["total_price"]
    try:
        result = user_table.get_item(Key={"userId": data["userId"]})
        user = result["Item"]
        points = user["points"]
        if total_price["total_price"] > points:
            deductPoints(data["userId"])
            total_price["total_price"] -= points
            total_price.update(points=points)
            return total_price
        else:
            raise Exception('price cannot be smaller than points')
    except Exception as e:
        raise e


def billCustomer(data, context):
    LOGGER.info(context.function_name)
    LOGGER.info("Inputs %s", data)
    return "Successfully billed"


def restoreRedeemPoints(data, context):
    LOGGER.info(context.function_name)
    LOGGER.info("Inputs %s", data)
    try:
        if data["total"]["points"]:
            user_table.update_item(Key={"userId": data["userId"]}, UpdateExpression='set points=:restored_points',
                                   ExpressionAttributesValues={":restored_points": data["total"]["points"]})
    except Exception as e:
        raise e


def restoreQuantity(data, context):
    LOGGER.info(context.function_name)
    LOGGER.info("Inputs %s", data)
    book_table.update_item(Key={"bookId": data["bookId"]}, UpdateExpression="SET quantity=quantity+:restoredQuantity",
                           ExpressionAttributeValues={":restoredQuantity": data["quantity"]})
    return "Quantity Restored"


def updateBookQuantity(book_id, order_quantity):
    LOGGER.info("book Id: %s", book_id)
    LOGGER.info("order quantity: %s", order_quantity)
    book_table.update_item(Key={"bookId": book_id}, UpdateExpression="SET quantity=:new_quantity",
                           ExpressionAttributeValues={":new_quantity": order_quantity})


def sqsWorker(event, context):
    try:
        LOGGER.info("Sqs events: %s", event)
        records = event["Records"][0]
        body = json.loads(records["body"])
        courier = "saatwikmehta@gmail.com"
        updateBookQuantity(body["Input"]["bookId"], body["Input"]["quantity"])

        step_function.send_task_success(taskToken=body["Token"], output=json.dumps({"email": courier}))
    except Exception as e:
        LOGGER.error("You Got an Error")
        LOGGER.error(e)
        step_function.send_task_failure(taskToke=body["Token"], error="NoCourierAvailable",
                                        cause="No couriers are available")
