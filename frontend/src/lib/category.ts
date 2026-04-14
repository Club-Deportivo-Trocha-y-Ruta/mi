import type { Sex } from "@/types/enums";

interface CategoryRule {
  minYear?: number;
  maxYear?: number;
  male?: string;
  female?: string;
  unisex?: string;
}

const CATEGORY_RULES: CategoryRule[] = [
  { minYear: 2022, unisex: "Teteros con pedales" },
  { minYear: 2020, maxYear: 2021, male: "Pre-Infantil A", female: "Pre-Infantil A femenino" },
  { minYear: 2018, maxYear: 2019, male: "Pre-Infantil B", female: "Pre-Infantil B femenino" },
  { minYear: 2016, maxYear: 2017, male: "Infantil A", female: "Infantil A femenino" },
  { minYear: 2014, maxYear: 2015, male: "Infantil B", female: "Infantil B femenino" },
  { minYear: 2012, maxYear: 2013, male: "Pre-juvenil A", female: "Pre-juvenil A femenino" },
  { minYear: 2010, maxYear: 2011, male: "Pre-juvenil B", female: "Pre-juvenil B femenino" },
  { minYear: 2008, maxYear: 2009, male: "Junior", female: "Junior femenino" },
  { maxYear: 2007, male: "Elite", female: "Elite femenina" },
];

export function computeAgeDecimal(birthDate: Date, referenceDate = new Date()): number {
  const millisPerYear = 1000 * 60 * 60 * 24 * 365.25;
  return Number(((referenceDate.getTime() - birthDate.getTime()) / millisPerYear).toFixed(1));
}

export function getCategory(birthYear: number, sex: Sex): string {
  const category = CATEGORY_RULES.find((rule) => {
    const matchesMin = rule.minYear === undefined || birthYear >= rule.minYear;
    const matchesMax = rule.maxYear === undefined || birthYear <= rule.maxYear;
    return matchesMin && matchesMax;
  });

  if (!category) {
    return "Categoria no definida";
  }

  if (category.unisex) {
    return category.unisex;
  }

  const fallback = category.male ?? category.unisex ?? "Categoria no definida";
  return sex === "F" ? (category.female ?? fallback) : fallback;
}
