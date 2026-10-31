from exile.model import Plugin


class Workshop(Plugin):
    id,name,category='workshop','Item workshop','Economy'
    description='Enable the item workshop in the left navigation to review the latest Alt+F item, assess copied items and give rating feedback.'

    def tick(self,snapshot,ctx):
        return []


def create_plugin():
    return Workshop()
