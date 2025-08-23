import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.course.models import Achievement, Course, Language, Vocabulary

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Setup the course system with initial data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--create-sample-data",
            action="store_true",
            help="Create sample courses and content",
        )
        parser.add_argument(
            "--create-achievements",
            action="store_true",
            help="Create default achievements",
        )
        parser.add_argument(
            "--create-languages",
            action="store_true",
            help="Create popular languages",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Setup everything",
        )

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                if options["all"]:
                    options["create_languages"] = True
                    options["create_achievements"] = True
                    options["create_sample_data"] = True

                if options["create_languages"]:
                    self.create_languages()

                if options["create_achievements"]:
                    self.create_achievements()

                if options["create_sample_data"]:
                    self.create_sample_data()

                self.stdout.write(
                    self.style.SUCCESS("Course system setup completed successfully!")
                )

        except Exception as e:
            logger.error(f"Error setting up course system: {str(e)}", exc_info=True)
            raise CommandError(f"Setup failed: {str(e)}")

    def create_languages(self):
        """Create popular languages for learning"""
        languages_data = [
            {
                "name": "English",
                "code": "en",
                "native_name": "English",
                "flag_emoji": "🇺🇸",
                "difficulty_rating": 2,
                "speakers_count": 1500000000,
                "script": "Latin",
            },
            {
                "name": "Spanish",
                "code": "es",
                "native_name": "Español",
                "flag_emoji": "🇪🇸",
                "difficulty_rating": 2,
                "speakers_count": 500000000,
                "script": "Latin",
            },
            {
                "name": "French",
                "code": "fr",
                "native_name": "Français",
                "flag_emoji": "🇫🇷",
                "difficulty_rating": 3,
                "speakers_count": 280000000,
                "script": "Latin",
            },
            {
                "name": "German",
                "code": "de",
                "native_name": "Deutsch",
                "flag_emoji": "🇩🇪",
                "difficulty_rating": 4,
                "speakers_count": 130000000,
                "script": "Latin",
            },
            {
                "name": "Chinese (Mandarin)",
                "code": "zh",
                "native_name": "中文",
                "flag_emoji": "🇨🇳",
                "difficulty_rating": 5,
                "speakers_count": 900000000,
                "script": "Chinese",
            },
            {
                "name": "Japanese",
                "code": "ja",
                "native_name": "日本語",
                "flag_emoji": "🇯🇵",
                "difficulty_rating": 5,
                "speakers_count": 125000000,
                "script": "Japanese",
            },
            {
                "name": "Korean",
                "code": "ko",
                "native_name": "한국어",
                "flag_emoji": "🇰🇷",
                "difficulty_rating": 4,
                "speakers_count": 77000000,
                "script": "Korean",
            },
            {
                "name": "Portuguese",
                "code": "pt",
                "native_name": "Português",
                "flag_emoji": "🇵🇹",
                "difficulty_rating": 2,
                "speakers_count": 260000000,
                "script": "Latin",
            },
            {
                "name": "Italian",
                "code": "it",
                "native_name": "Italiano",
                "flag_emoji": "🇮🇹",
                "difficulty_rating": 2,
                "speakers_count": 65000000,
                "script": "Latin",
            },
            {
                "name": "Russian",
                "code": "ru",
                "native_name": "Русский",
                "flag_emoji": "🇷🇺",
                "difficulty_rating": 4,
                "speakers_count": 260000000,
                "script": "Cyrillic",
            },
            {
                "name": "Arabic",
                "code": "ar",
                "native_name": "العربية",
                "flag_emoji": "🇸🇦",
                "difficulty_rating": 5,
                "speakers_count": 420000000,
                "script": "Arabic",
                "is_rtl": True,
            },
            {
                "name": "Hindi",
                "code": "hi",
                "native_name": "हिन्दी",
                "flag_emoji": "🇮🇳",
                "difficulty_rating": 4,
                "speakers_count": 600000000,
                "script": "Devanagari",
            },
        ]

        created_count = 0
        for lang_data in languages_data:
            language, created = Language.objects.get_or_create(
                code=lang_data["code"], defaults=lang_data
            )
            if created:
                created_count += 1
                self.stdout.write(f"Created language: {language.name}")

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} languages"))

    def create_achievements(self):
        """Create default achievements"""
        achievements_data = [
            {
                "name": "First Steps",
                "description": "Complete your first lesson",
                "category": "progress",
                "xp_reward": 50,
                "rarity": "common",
                "criteria": {"lessons_completed": 1},
                "icon_name": "star",
            },
            {
                "name": "Streak Master",
                "description": "Maintain a 7-day learning streak",
                "category": "streak",
                "xp_reward": 200,
                "rarity": "uncommon",
                "criteria": {"min_streak_days": 7},
                "icon_name": "fire",
            },
            {
                "name": "Course Conqueror",
                "description": "Complete your first course",
                "category": "progress",
                "xp_reward": 500,
                "rarity": "rare",
                "criteria": {"courses_completed": 1},
                "icon_name": "trophy",
            },
            {
                "name": "Perfect Score",
                "description": "Get 100% on an assessment",
                "category": "performance",
                "xp_reward": 100,
                "rarity": "uncommon",
                "criteria": {"perfect_assessment": True},
                "icon_name": "medal",
            },
            {
                "name": "Social Learner",
                "description": "Participate in 10 discussions",
                "category": "social",
                "xp_reward": 150,
                "rarity": "uncommon",
                "criteria": {"discussions_participated": 10},
                "icon_name": "chat",
            },
            {
                "name": "XP Champion",
                "description": "Earn 10,000 XP",
                "category": "progress",
                "xp_reward": 1000,
                "rarity": "epic",
                "criteria": {"total_xp": 10000},
                "icon_name": "crown",
            },
            {
                "name": "Vocabulary Master",
                "description": "Learn 500 vocabulary words",
                "category": "mastery",
                "xp_reward": 750,
                "rarity": "epic",
                "criteria": {"vocabulary_learned": 500},
                "icon_name": "book",
            },
            {
                "name": "Speed Learner",
                "description": "Complete 5 lessons in one day",
                "category": "challenge",
                "xp_reward": 300,
                "rarity": "rare",
                "criteria": {"daily_lessons": 5},
                "icon_name": "bolt",
            },
            {
                "name": "Dedication",
                "description": "Maintain a 30-day learning streak",
                "category": "streak",
                "xp_reward": 1000,
                "rarity": "legendary",
                "criteria": {"min_streak_days": 30},
                "icon_name": "flame",
            },
            {
                "name": "Polyglot",
                "description": "Complete courses in 3 different languages",
                "category": "exploration",
                "xp_reward": 2000,
                "rarity": "legendary",
                "criteria": {"languages_learned": 3},
                "icon_name": "globe",
            },
        ]

        created_count = 0
        for achievement_data in achievements_data:
            achievement, created = Achievement.objects.get_or_create(
                name=achievement_data["name"], defaults=achievement_data
            )
            if created:
                created_count += 1
                self.stdout.write(f"Created achievement: {achievement.name}")

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} achievements"))

    def create_sample_data(self):
        """Create sample courses and content"""
        # Get or create English and Spanish languages
        english, _ = Language.objects.get_or_create(
            code="en",
            defaults={
                "name": "English",
                "native_name": "English",
                "difficulty_rating": 2,
            },
        )

        spanish, _ = Language.objects.get_or_create(
            code="es",
            defaults={
                "name": "Spanish",
                "native_name": "Español",
                "difficulty_rating": 2,
            },
        )

        # Create sample admin user if it doesn't exist
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.create_user(
                username="admin",
                email="admin@example.com",
                is_staff=True,
                is_superuser=True,
            )
            admin_user.set_password("admin123")
            admin_user.save()

        # Create sample Spanish course
        spanish_course, created = Course.objects.get_or_create(
            title="Spanish for Beginners",
            target_language=spanish,
            defaults={
                "description": "Learn Spanish from scratch with interactive lessons and real-world practice.",
                "short_description": "Start your Spanish journey today!",
                "level": "beginner",
                "category": "general",
                "estimated_duration_hours": 40,
                "instructor": admin_user,
                "is_free": True,
                "is_published": True,
                "difficulty_score": 2.0,
                "base_language": english,
            },
        )

        if created:
            self.stdout.write(f"Created course: {spanish_course.title}")

            # Create sample vocabulary
            vocabulary_data = [
                {
                    "word": "hola",
                    "translation": "hello",
                    "part_of_speech": "interjection",
                },
                {
                    "word": "gracias",
                    "translation": "thank you",
                    "part_of_speech": "noun",
                },
                {"word": "agua", "translation": "water", "part_of_speech": "noun"},
                {"word": "casa", "translation": "house", "part_of_speech": "noun"},
                {"word": "comer", "translation": "to eat", "part_of_speech": "verb"},
            ]

            for vocab_data in vocabulary_data:
                vocab, vocab_created = Vocabulary.objects.get_or_create(
                    word=vocab_data["word"],
                    language=spanish,
                    defaults={
                        "translation": vocab_data["translation"],
                        "part_of_speech": vocab_data["part_of_speech"],
                        "frequency_rating": 5,
                        "difficulty_level": 1,
                    },
                )
                if vocab_created:
                    self.stdout.write(f"Created vocabulary: {vocab.word}")

        # Create sample English course for Spanish speakers
        english_course, created = Course.objects.get_or_create(
            title="English for Spanish Speakers",
            target_language=english,
            defaults={
                "description": "Learn English with explanations in Spanish.",
                "short_description": "Aprende inglés desde el español",
                "level": "beginner",
                "category": "general",
                "estimated_duration_hours": 50,
                "instructor": admin_user,
                "is_free": True,
                "is_published": True,
                "difficulty_score": 2.5,
                "base_language": spanish,
            },
        )

        if created:
            self.stdout.write(f"Created course: {english_course.title}")

        self.stdout.write(self.style.SUCCESS("Sample data created successfully"))
