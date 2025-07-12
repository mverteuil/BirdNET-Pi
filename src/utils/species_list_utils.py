import os


class SpeciesListUtils:
    def __init__(self, species_list_path: str):
        self.species_list_path = species_list_path
        self._species_list = None

    def load_species_list(self) -> list[str]:
        if self._species_list is not None:
            return self._species_list

        if not os.path.exists(self.species_list_path):
            raise FileNotFoundError(
                f"Species list file not found at: {self.species_list_path}"
            )

        species = []
        with open(self.species_list_path, "r", encoding="utf-8") as f:
            for line in f:
                species.append(line.strip())
        self._species_list = species
        return species

    def is_valid_species(self, species_name: str) -> bool:
        if self._species_list is None:
            self.load_species_list()
        return species_name in self._species_list

    def get_species_count(self) -> int:
        if self._species_list is None:
            self.load_species_list()
        return len(self._species_list)
