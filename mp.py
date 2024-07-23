import multiprocessing
import multiprocessing.managers
from sortedcontainers import SortedDict


class MyClass:
    def __init__(self, value, dict1, dict2):
        self.integer = value
        self.dict1 = dict1
        self.dict2 = dict2


def my_class_factory(value, manager):
    dict1 = manager.SortedDict()
    dict2 = manager.SortedDict()
    return MyClass(value, dict1, dict2)


def worker(shared_instance):
    shared_instance.integer += 1
    shared_instance.dict1['b'] = 2
    shared_instance.dict1['a'] = 1
    shared_instance.dict2['d'] = 4
    shared_instance.dict2['c'] = 3


if __name__ == "__main__":
    manager = multiprocessing.managers.SyncManager()

    # Register the custom SortedDict
    manager.register('SortedDict', SortedDict, exposed=('__setitem__', '__getitem__', '__delitem__', 'values', 'keys',))
    manager.start()

    # Create an instance of MyClass through the factory function
    shared_instance = my_class_factory(42, manager)

    # Start a process that modifies the shared instance
    process = multiprocessing.Process(target=worker, args=(shared_instance,))
    process.start()
    process.join()

    # Access the modified shared instance
    print(shared_instance.integer)  # Output: 43
    print(shared_instance.dict1)    # Output: SortedDict([('a', 1), ('b', 2)])
    print(shared_instance.dict2)    # Output: SortedDict([('c', 3), ('d', 4)])
