from django.db.models import Q
from django_filters import rest_framework as filters

from .models import Connection, Experience, Project, Skill, User, UserProfile


class UserFilter(filters.FilterSet):
    """
    Advanced filtering for User model with comprehensive search capabilities
    """

    # Basic user filters
    username = filters.CharFilter(lookup_expr="icontains")
    email = filters.CharFilter(lookup_expr="icontains")
    first_name = filters.CharFilter(lookup_expr="icontains")
    last_name = filters.CharFilter(lookup_expr="icontains")
    is_active = filters.BooleanFilter()
    is_verified = filters.BooleanFilter()
    is_staff = filters.BooleanFilter()

    # Profile-based filters
    location = filters.CharFilter(
        field_name="profile__location", lookup_expr="icontains"
    )
    current_company = filters.CharFilter(
        field_name="profile__current_company", lookup_expr="icontains"
    )
    current_position = filters.CharFilter(
        field_name="profile__current_position", lookup_expr="icontains"
    )
    headline = filters.CharFilter(
        field_name="profile__headline", lookup_expr="icontains"
    )
    bio = filters.CharFilter(field_name="profile__bio", lookup_expr="icontains")

    # Status filters
    status = filters.ChoiceFilter(
        field_name="profile__status", choices=User.UserStatus.choices
    )
    is_online = filters.BooleanFilter(field_name="profile__is_online")
    profile_visibility = filters.ChoiceFilter(
        field_name="profile__profile_visibility",
        choices=UserProfile.ProfileVisibility.choices,
    )

    # Skill-based filters
    skills = filters.CharFilter(method="filter_by_skills")
    skill_level = filters.NumberFilter(method="filter_by_skill_level")
    years_of_experience = filters.NumberFilter(
        field_name="profile__years_of_experience"
    )

    # Experience-based filters
    company = filters.CharFilter(method="filter_by_company")
    position = filters.CharFilter(method="filter_by_position")
    industry = filters.CharFilter(method="filter_by_industry")

    # Education-based filters
    university = filters.CharFilter(method="filter_by_university")
    degree = filters.CharFilter(method="filter_by_degree")
    field_of_study = filters.CharFilter(method="filter_by_field_of_study")

    # Language filters
    languages = filters.CharFilter(method="filter_by_languages")
    language_proficiency = filters.ChoiceFilter(method="filter_by_language_proficiency")

    # Date filters
    joined_after = filters.DateFilter(field_name="date_joined", lookup_expr="gte")
    joined_before = filters.DateFilter(field_name="date_joined", lookup_expr="lte")
    last_login_after = filters.DateFilter(field_name="last_login", lookup_expr="gte")
    last_login_before = filters.DateFilter(field_name="last_login", lookup_expr="lte")
    last_activity_after = filters.DateTimeFilter(
        field_name="profile__last_activity", lookup_expr="gte"
    )
    last_activity_before = filters.DateTimeFilter(
        field_name="profile__last_activity", lookup_expr="lte"
    )

    # Connection-based filters
    has_connections = filters.BooleanFilter(method="filter_has_connections")
    mutual_connections = filters.CharFilter(method="filter_mutual_connections")
    connection_count_min = filters.NumberFilter(method="filter_connection_count_min")
    connection_count_max = filters.NumberFilter(method="filter_connection_count_max")

    # Geographic filters
    country = filters.CharFilter(method="filter_by_country")
    city = filters.CharFilter(method="filter_by_city")
    timezone = filters.CharFilter(field_name="profile__timezone")

    # Achievement filters
    has_achievements = filters.BooleanFilter(method="filter_has_achievements")
    achievement_category = filters.CharFilter(method="filter_by_achievement_category")

    # Project filters
    has_projects = filters.BooleanFilter(method="filter_has_projects")
    project_technology = filters.CharFilter(method="filter_by_project_technology")

    # Profile completeness
    profile_completeness_min = filters.NumberFilter(
        method="filter_profile_completeness_min"
    )
    has_avatar = filters.BooleanFilter(method="filter_has_avatar")
    has_bio = filters.BooleanFilter(method="filter_has_bio")

    # Full text search
    search = filters.CharFilter(method="filter_full_text_search")

    class Meta:
        model = User
        fields = []

    def filter_by_skills(self, queryset, name, value):
        """Filter users by skills (comma-separated)"""
        if not value:
            return queryset

        skills = [skill.strip() for skill in value.split(",")]
        return queryset.filter(skills__name__in=skills).distinct()

    def filter_by_skill_level(self, queryset, name, value):
        """Filter users by minimum skill level"""
        if not value:
            return queryset

        return queryset.filter(skills__level__gte=value).distinct()

    def filter_by_company(self, queryset, name, value):
        """Filter by current or past company"""
        if not value:
            return queryset

        return queryset.filter(
            Q(profile__current_company__icontains=value)
            | Q(experience__company__icontains=value)
        ).distinct()

    def filter_by_position(self, queryset, name, value):
        """Filter by current or past position"""
        if not value:
            return queryset

        return queryset.filter(
            Q(profile__current_position__icontains=value)
            | Q(experience__title__icontains=value)
        ).distinct()

    def filter_by_industry(self, queryset, name, value):
        """Filter by industry based on experience"""
        if not value:
            return queryset

        return queryset.filter(experience__industry__icontains=value).distinct()

    def filter_by_university(self, queryset, name, value):
        """Filter by university/institution"""
        if not value:
            return queryset

        return queryset.filter(educations__institution__icontains=value).distinct()

    def filter_by_degree(self, queryset, name, value):
        """Filter by degree"""
        if not value:
            return queryset

        return queryset.filter(educations__degree__icontains=value).distinct()

    def filter_by_field_of_study(self, queryset, name, value):
        """Filter by field of study"""
        if not value:
            return queryset

        return queryset.filter(educations__field_of_study__icontains=value).distinct()

    def filter_by_languages(self, queryset, name, value):
        """Filter by languages (comma-separated)"""
        if not value:
            return queryset

        languages = [lang.strip() for lang in value.split(",")]
        return queryset.filter(languages__name__in=languages).distinct()

    def filter_by_language_proficiency(self, queryset, name, value):
        """Filter by minimum language proficiency"""
        if not value:
            return queryset

        proficiency_order = ["basic", "conversational", "fluent", "native"]
        try:
            min_index = proficiency_order.index(value)
            valid_proficiencies = proficiency_order[min_index:]
            return queryset.filter(
                languages__proficiency__in=valid_proficiencies
            ).distinct()
        except ValueError:
            return queryset

    def filter_has_connections(self, queryset, name, value):
        """Filter users who have connections"""
        if value is None:
            return queryset

        if value:
            return queryset.filter(
                Q(connections_sent__status="accepted")
                | Q(connections_received__status="accepted")
            ).distinct()
        else:
            return queryset.exclude(
                Q(connections_sent__status="accepted")
                | Q(connections_received__status="accepted")
            ).distinct()

    def filter_mutual_connections(self, queryset, name, value):
        """Filter by users with mutual connections to specified user ID"""
        if not value:
            return queryset

        try:
            user_id = int(value)
            # Get connections of the specified user
            user_connections = (
                User.objects.get(id=user_id)
                .connections_sent.filter(status="accepted")
                .values_list("to_user_id", flat=True)
            )

            # Find users connected to those connections
            return (
                queryset.filter(
                    Q(connections_sent__to_user_id__in=user_connections)
                    | Q(connections_received__from_user_id__in=user_connections)
                )
                .exclude(id=user_id)
                .distinct()
            )
        except (ValueError, User.DoesNotExist):
            return queryset

    def filter_connection_count_min(self, queryset, name, value):
        """Filter by minimum connection count"""
        if not value:
            return queryset

        from django.db.models import Count

        return queryset.annotate(
            connection_count=Count(
                "connections_sent", filter=Q(connections_sent__status="accepted")
            )
            + Count(
                "connections_received",
                filter=Q(connections_received__status="accepted"),
            )
        ).filter(connection_count__gte=value)

    def filter_connection_count_max(self, queryset, name, value):
        """Filter by maximum connection count"""
        if not value:
            return queryset

        from django.db.models import Count

        return queryset.annotate(
            connection_count=Count(
                "connections_sent", filter=Q(connections_sent__status="accepted")
            )
            + Count(
                "connections_received",
                filter=Q(connections_received__status="accepted"),
            )
        ).filter(connection_count__lte=value)

    def filter_by_country(self, queryset, name, value):
        """Filter by country (extracted from location)"""
        if not value:
            return queryset

        return queryset.filter(profile__location__icontains=value)

    def filter_by_city(self, queryset, name, value):
        """Filter by city (extracted from location)"""
        if not value:
            return queryset

        return queryset.filter(profile__location__icontains=value)

    def filter_has_achievements(self, queryset, name, value):
        """Filter users who have achievements"""
        if value is None:
            return queryset

        if value:
            return queryset.filter(achievements__isnull=False).distinct()
        else:
            return queryset.filter(achievements__isnull=True).distinct()

    def filter_by_achievement_category(self, queryset, name, value):
        """Filter by achievement category"""
        if not value:
            return queryset

        return queryset.filter(achievements__category=value).distinct()

    def filter_has_projects(self, queryset, name, value):
        """Filter users who have projects"""
        if value is None:
            return queryset

        if value:
            return queryset.filter(projects__isnull=False).distinct()
        else:
            return queryset.filter(projects__isnull=True).distinct()

    def filter_by_project_technology(self, queryset, name, value):
        """Filter by project technologies"""
        if not value:
            return queryset

        technologies = [tech.strip() for tech in value.split(",")]
        return queryset.filter(projects__technologies__overlap=technologies).distinct()

    def filter_profile_completeness_min(self, queryset, name, value):
        """Filter by minimum profile completeness percentage"""
        if not value:
            return queryset

        # This would require a custom database function or annotation
        # For now, we'll filter by presence of key fields
        conditions = Q()

        if value >= 20:
            conditions &= Q(profile__bio__isnull=False, profile__bio__gt="")
        if value >= 40:
            conditions &= Q(profile__avatar__isnull=False)
        if value >= 60:
            conditions &= Q(experience__isnull=False)
        if value >= 80:
            conditions &= Q(skills__isnull=False)

        return queryset.filter(conditions).distinct()

    def filter_has_avatar(self, queryset, name, value):
        """Filter users who have profile pictures"""
        if value is None:
            return queryset

        if value:
            return queryset.filter(profile__avatar__isnull=False)
        else:
            return queryset.filter(profile__avatar__isnull=True)

    def filter_has_bio(self, queryset, name, value):
        """Filter users who have bio"""
        if value is None:
            return queryset

        if value:
            return queryset.filter(profile__bio__isnull=False, profile__bio__gt="")
        else:
            return queryset.filter(Q(profile__bio__isnull=True) | Q(profile__bio=""))

    def filter_full_text_search(self, queryset, name, value):
        """Full text search across multiple fields"""
        if not value:
            return queryset

        search_terms = value.split()
        conditions = Q()

        for term in search_terms:
            term_conditions = (
                Q(username__icontains=term)
                | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(email__icontains=term)
                | Q(profile__headline__icontains=term)
                | Q(profile__bio__icontains=term)
                | Q(profile__current_company__icontains=term)
                | Q(profile__current_position__icontains=term)
                | Q(profile__location__icontains=term)
                | Q(skills__name__icontains=term)
                | Q(experience__title__icontains=term)
                | Q(experience__company__icontains=term)
                | Q(educations__institution__icontains=term)
                | Q(educations__degree__icontains=term)
                | Q(projects__title__icontains=term)
            )
            conditions |= term_conditions

        return queryset.filter(conditions).distinct()


class ConnectionFilter(filters.FilterSet):
    """Filter for Connection model"""

    status = filters.ChoiceFilter(field_name="status")
    from_user = filters.NumberFilter(field_name="from_user_id")
    to_user = filters.NumberFilter(field_name="to_user_id")
    created_after = filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Connection
        fields = ["status", "from_user", "to_user"]


class SkillFilter(filters.FilterSet):
    """Filter for Skill model"""

    name = filters.CharFilter(lookup_expr="icontains")
    category = filters.CharFilter(lookup_expr="icontains")
    level = filters.NumberFilter()
    level_min = filters.NumberFilter(field_name="level", lookup_expr="gte")
    level_max = filters.NumberFilter(field_name="level", lookup_expr="lte")
    years_of_experience = filters.NumberFilter()
    years_min = filters.NumberFilter(
        field_name="years_of_experience", lookup_expr="gte"
    )
    years_max = filters.NumberFilter(
        field_name="years_of_experience", lookup_expr="lte"
    )
    is_endorsed = filters.BooleanFilter()

    class Meta:
        model = Skill
        fields = ["name", "category", "level", "years_of_experience", "is_endorsed"]


class ExperienceFilter(filters.FilterSet):
    """Filter for Experience model"""

    title = filters.CharFilter(lookup_expr="icontains")
    company = filters.CharFilter(lookup_expr="icontains")
    location = filters.CharFilter(lookup_expr="icontains")
    type = filters.ChoiceFilter()
    is_current = filters.BooleanFilter()
    start_date_after = filters.DateFilter(field_name="start_date", lookup_expr="gte")
    start_date_before = filters.DateFilter(field_name="start_date", lookup_expr="lte")
    end_date_after = filters.DateFilter(field_name="end_date", lookup_expr="gte")
    end_date_before = filters.DateFilter(field_name="end_date", lookup_expr="lte")

    class Meta:
        model = Experience
        fields = ["title", "company", "location", "type", "is_current"]


class ProjectFilter(filters.FilterSet):
    """Filter for Project model"""

    title = filters.CharFilter(lookup_expr="icontains")
    category = filters.ChoiceFilter()
    status = filters.ChoiceFilter()
    technologies = filters.CharFilter(method="filter_by_technologies")
    start_date_after = filters.DateFilter(field_name="start_date", lookup_expr="gte")
    start_date_before = filters.DateFilter(field_name="start_date", lookup_expr="lte")
    is_current = filters.BooleanFilter()

    class Meta:
        model = Project
        fields = ["title", "category", "status", "is_current"]

    def filter_by_technologies(self, queryset, name, value):
        """Filter by technologies used in projects"""
        if not value:
            return queryset

        technologies = [tech.strip() for tech in value.split(",")]
        return queryset.filter(technologies__overlap=technologies)
