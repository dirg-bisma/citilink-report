from django import template
from django.contrib.auth.models import Group
from django.contrib.admin.views.main import PAGE_VAR

register = template.Library()


@register.simple_tag
def get_all_groups():
    return Group.objects.all()


@register.simple_tag
def get_page_info(cl):
    """
    Computes pagination details for changelist:
    - current page_num (1-indexed)
    - num_pages
    - start_index & end_index of displayed records
    - 4-number page window
    - prev/next/first/last urls
    """
    paginator = cl.paginator
    num_pages = paginator.num_pages
    page_num = getattr(cl, 'page_num', 1)
    if hasattr(page_num, 'number'):
        page_num = page_num.number
    else:
        try:
            page_num = int(page_num)
        except (ValueError, TypeError):
            page_num = 1

    result_count = cl.result_count
    list_per_page = cl.list_per_page

    if result_count > 0:
        start_index = (page_num - 1) * list_per_page + 1
        end_index = min(page_num * list_per_page, result_count)
    else:
        start_index = 0
        end_index = 0

    # Window of max 4 page numbers
    if num_pages <= 4:
        page_range_4 = list(range(1, num_pages + 1))
    else:
        start = max(1, page_num - 1)
        if start + 3 > num_pages:
            start = num_pages - 3
        page_range_4 = list(range(start, start + 4))

    page_param = getattr(cl.model._meta, 'model_name', '') + "-p" if hasattr(cl, "dataset") else PAGE_VAR

    def get_url(p):
        return cl.get_query_string({page_param: p})

    return {
        'page_num': page_num,
        'num_pages': num_pages,
        'start_index': start_index,
        'end_index': end_index,
        'result_count': result_count,
        'full_result_count': cl.full_result_count,
        'has_previous': page_num > 1,
        'has_next': page_num < num_pages,
        'first_url': get_url(1),
        'prev_url': get_url(page_num - 1) if page_num > 1 else '#',
        'next_url': get_url(page_num + 1) if page_num < num_pages else '#',
        'last_url': get_url(num_pages),
        'page_numbers': [{'number': p, 'url': get_url(p), 'is_current': p == page_num} for p in page_range_4],
        'is_filtered': cl.result_count != cl.full_result_count,
        'pagination_required': cl.result_count > list_per_page,
    }
