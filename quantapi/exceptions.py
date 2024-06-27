# In your_project/exceptions.py
import traceback
from attr import has
from rest_framework.views import exception_handler
from rest_framework import serializers
from rest_framework.response import Response

from quantapi.validations import InvalidRequestError


def ValidationErrorHandler(exc: Exception, context):
    response = exception_handler(exc, context)
    detail = str(exc)
    tb = traceback.format_exc()
    if not response:
        response = Response({'detail': detail, 'traceback': tb}, status=500)
    if not response.data:
        response.data = {'detail': detail, 'traceback': tb}

    if hasattr(exc, 'status_code'):
        response.status_code = exc.status_code  # type: ignore
    if hasattr(exc, 'detail'):
        response.data['detail'] = detail  # type: ignore

    return response
