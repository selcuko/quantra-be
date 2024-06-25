# In your_project/exceptions.py
from rest_framework.views import exception_handler
from rest_framework import serializers
from rest_framework.response import Response

def ValidationErrorHandler(exc: Exception, context):
    return Response({'detail': str(exc)}, status=400)
