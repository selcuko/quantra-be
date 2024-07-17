import logging
from incident.groups import Groups


class Severity:
    Critical = "CRITICAL"
    Minor = "MINOR"


class IssueBase(Exception):
    send_to = Groups.Nobody
    issue_worthy = False

    def __init__(self):
        if not hasattr(self, 'message'):
            self.message = 'Unspecified issue occurred.'
        self.handle()

    def __str__(self):
        return self.message

    def handle(self):
        self.log()
        self.notify()
        if self.issue_worthy:
            self.issue()

    def issue(self):
        print(f"Issue created for {self.__class__.__name__}:\n\t{self.message}")

    def log(self):
        logging.error(self.message)

    def notify(self):
        print(f"Notification sent to {self.get_send_to()} for {self.__class__.__name__}:\n\t{self.message}")

    @classmethod
    def get_send_to(cls):
        return cls.send_to
