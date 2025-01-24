import json
import os
from django.core.management.base import BaseCommand
from quantapi.models import GlobalSymbol, Tag


class Command(BaseCommand):
    help = 'Match Tags to GlobalSymbols'

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        folder = 'cg-payloads'
        files =  os.listdir(folder)
        tag_through_bulk = []
        errors = []
        self.stdout.write("Loading every GlobalSymbol", ending="\t")
        gs = {gs.cid: gs for gs in GlobalSymbol.objects.all()}
        tags = Tag.objects.all()
        bulk_size = 500
        self.stdout.write(self.style.SUCCESS("OK"))

        for gs_id, gs in gs.items():
            self.stdout.write(f"Processing {gs_id}", ending="\t")
            if not os.path.exists(f"{folder}/{gs_id}.json"):
                self.stdout.write(self.style.ERROR("NO PAYLOAD"))
                errors.append(gs_id)
                continue
            with open(f"{folder}/{gs_id}.json") as f:
                payload = json.load(f)
                tag_ids = [tag.pk for tag in tags if tag.display in payload['categories']]
                for tag in tag_ids:
                    tag_through_bulk.append(gs.tags.through(tag_id=tag, globalsymbol_id=gs.pk))
            self.stdout.write(self.style.SUCCESS("QUEUED"))
            if len(tag_through_bulk) >= bulk_size:
                self.stdout.write("COMMITTING", ending="\t")
                created = gs.tags.through.objects.bulk_create(tag_through_bulk, ignore_conflicts=True)
                self.stdout.write(self.style.SUCCESS(f"CREATED {len(created)} ASSOCIATIONS"))
                tag_through_bulk = []

        if  tag_through_bulk:
            self.stdout.write("COMMITTING", ending="\t")
            created = GlobalSymbol.tags.through.objects.bulk_create(tag_through_bulk, ignore_conflicts=True)
            self.stdout.write(self.style.SUCCESS(f"CREATED {len(created)} ASSOCIATIONS"))
            tag_through_bulk = []
        self.stdout.write(self.style.SUCCESS(f"Errors: {errors}"))


