from django.db.models import F
from django_filters import filters


class NullsLastOrderingFilter(filters.OrderingFilter):
    def __init__(self, *args, **kwargs):
        self.nulls_last = kwargs.pop('nulls_last', [])
        super().__init__(*args, **kwargs)
        self.fields = kwargs.get('fields', {})
        

    def filter(self, qs, value):
        result = super().filter(qs, value)
        if not value:
            return result

        ordering = []
        for order_field in value:
            is_desc = order_field.startswith('-')
            field_name = order_field.lstrip('-')

            if field_name in self.fields and field_name in self.nulls_last:
                model_field = field_name
                if is_desc:
                    ordering.append(F(model_field).desc(nulls_last=True))
                else:
                    ordering.append(F(model_field).asc(nulls_last=True))
            else:
                ordering.append(order_field)

        return qs.order_by(*ordering)
