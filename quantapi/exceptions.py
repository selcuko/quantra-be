# In your_project/exceptions.py
import traceback
from attr import has
from rest_framework.views import exception_handler
from rest_framework import serializers
from rest_framework.response import Response

from quantapi.validations import InvalidRequestError


def ValidationErrorHandler(exc: Exception, context):
    response = Response({
        'detail': str(exc),
        'traceback': traceback.format_exc(),
    }, status=500)

    if hasattr(exc, 'status_code'):
        response.status_code = exc.status_code  # type: ignore
    if hasattr(exc, 'detail'):
        response.data['detail'] = exc.detail  # type: ignore

    return response
